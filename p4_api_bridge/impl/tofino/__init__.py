import json
import logging
import re
import socket
from typing import Dict, List, Optional, Union

from p4_api_bridge import ApiBridge, SwitchApiError

_logger: logging.Logger = logging.getLogger(__name__)


class TofinoShellApiBridge(ApiBridge):
    def __init__(self, switch: str, p4_program_name: str, port: int, interface_to_port: Dict[str, int],
                 enable_acknowledgments: bool) -> None:
        super().__init__(switch)
        _logger.debug(f"{self._switch}: P4 program: {p4_program_name}; send acknowledgments: {enable_acknowledgments}")
        _logger.debug(f"{self._switch}: Remote BF shell port: {port}")
        _logger.debug(f"{self._switch}: Interfaces: {interface_to_port}")
        self._p4_program_name: str = p4_program_name
        self._interface_to_port: Dict[str, int] = interface_to_port
        self._enable_acknowledgments: bool = enable_acknowledgments
        self._socket = None
        self._initialize_connection(port)  # Sets self._socket
        self._batch_counter: int = 0  # Nested batches aren't support by the BF shell, so we support them via a counter

    def _read_exactly_n_bytes(self, n: int) -> bytes:
        """Reads exactly n bytes from the socket."""
        buffer = bytearray(n)
        view = memoryview(buffer)
        total_read = 0
        while total_read != n:
            just_read = self._socket.recv_into(view[total_read:], n - total_read)
            total_read += just_read
            if just_read == 0:  # Socket closed
                return b''
        return buffer

    def _send_string(self, string: str) -> None:
        string = string.encode()
        msg_length = len(string).to_bytes(4, byteorder='big')
        self._socket.sendall(msg_length + string)

    def _initialize_connection(self, port: int) -> None:
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(10)
        self._socket.connect(("localhost", port))
        self._send_string(json.dumps({
            "program_name": self._p4_program_name,
            "enable_acknowledgments": self._enable_acknowledgments,
        }))

    def _forward_cmd(self, cmd: str) -> None:
        """Forwards the specified command to the remote BF shell."""
        self._send_string(cmd)
        if not self._enable_acknowledgments:
            return

        # Wait for a response: make sure the other side doesn't fall behind, wait for the command to get executed
        response = ''
        if (response_length := self._read_exactly_n_bytes(4)) != b'':
            response = self._read_exactly_n_bytes(int.from_bytes(response_length, byteorder='big')).decode()
        if len(response) == 0:  # Either the 1st or the 2nd read failed
            raise SwitchApiError(f"Error executing command '{cmd}': connection closed by the remote BF shell")
        if response != "OK":
            raise SwitchApiError(f"Error executing command '{cmd}': received response: {response}")

    def translate_interface_to_port(self, intf: str) -> Optional[int]:
        return self._interface_to_port.get(intf)

    def _translate_value_if_necessary(self, value: Union[str, int]) -> str:
        value = super()._translate_value_if_necessary(value)
        if re.match(r'^\d+..\d+$', value):  # Range match keys must be 2 separate values
            value = value.replace('..', '", "')
        value = '"' + value + '"'  # Quote strings
        return value

    def _close_impl(self) -> None:
        self._socket.close()

    def _reset_state_impl(self) -> None:
        _logger.error("'reset_state' is yet to be implemented for remote BF shell")

    def _batch_start_impl(self) -> None:
        if self._batch_counter == 0:
            self._forward_cmd("bfrt.batch_begin()")
        self._batch_counter += 1

    def _batch_stop_impl(self) -> None:
        if self._batch_counter == 0:
            raise SwitchApiError("More batches were stopped than started")
        self._batch_counter -= 1
        if self._batch_counter == 0:
            self._forward_cmd("bfrt.batch_end()")

    def _register_set_impl(self, register_name: str, index: int, value: str) -> None:
        self._forward_cmd(f"""
        p4.{register_name}.mod({index}, {value})
        p4.{register_name}.operation_register_sync()
        """)

    def _table_add_impl(self, table_name: str, match_keys: List[str], action_name: str,
                        action_params: List[str]) -> None:
        action_name = action_name.split('.')[-1]
        params = ', '.join(match_keys + action_params)
        self._forward_cmd(f'p4.{table_name}.add_with_{action_name}({params})')

    def _table_modify_impl(self, table_name: str, match_keys: List[str], action_name: str,
                           action_params: List[str]) -> None:
        action_name = action_name.split('.')[-1]
        params = ', '.join(match_keys + action_params)
        self._forward_cmd(f'p4.{table_name}.mod_with_{action_name}({params})')

    def _table_set_default_impl(self, table_name: str, action_name: str, action_params: List[str]) -> None:
        action_name = action_name.split('.')[-1]
        params = ', '.join(action_params)
        self._forward_cmd(f'p4.{table_name}.set_default_with_{action_name}({params})')

    def _table_delete_impl(self, table_name: str, match_keys: List[str]) -> None:
        params = ', '.join(match_keys)
        self._forward_cmd(f'p4.{table_name}.delete({params})')

    def _table_clear_impl(self, table_name: str) -> None:
        batch = self._batch_counter == 0  # Only batch if not already in a batch
        self._forward_cmd(f'p4.{table_name}.clear(batch={batch})')

    def _multicast_group_create_impl(self, group_id: int, members: List[ApiBridge.MulticastGroupMember]) -> None:
        raise NotImplementedError()

    def _clone_session_create_impl(self, session_id: int, members: List[ApiBridge.CloneSessionMember]) -> None:
        raise NotImplementedError()
