import json
import logging
import subprocess
from typing import Any, Dict, List, Optional

from p4_api_bridge import ApiBridge

_logger: logging.Logger = logging.getLogger(__name__)


class NikssCtlApiBridge(ApiBridge):
    def __init__(self, switch: str, pipeline_id: int) -> None:
        super().__init__(switch)
        self._pipeline: int = pipeline_id
        _logger.debug(f"{self._switch}: Pipeline ID: {self._pipeline}")
        self._interface_to_port: Dict[str, int] = self._query_ports()
        _logger.debug(f"{self._switch}: Interfaces: {self._interface_to_port}")

    def _run(self, cmd: str, throw_on_fail: bool = True, supress_stderr: bool = False) -> str:
        """
        Runs the specified NIKSS subcommand and returns the output. If enabled, throws an exception on failure.
        By default, anything written to stderr is logged as a warning. By setting 'supress_stderr' to True,
        these log entries are made at the debug level instead except if the command fails.
        """
        cmd = f"nikss-ctl {cmd}"
        _logger.debug(f"{self._switch}: Executing: {cmd}")
        proc = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _logger.debug(f"nikss-ctl stdout: {proc.stdout.decode()}")
        if len(proc.stderr) > 0:
            log = _logger.debug if supress_stderr and proc.returncode == 0 else _logger.warning
            log(f"nikss-ctl stderr: {proc.stderr.decode()}")
        if throw_on_fail:
            proc.check_returncode()
        return proc.stdout.decode()

    def _query_ports(self) -> Dict[str, int]:
        """Query which interface got which port ID."""
        config: Dict = json.loads(self._run(f"pipeline show id {self._pipeline}"))
        ports: List[Dict] = config["pipeline"]["ports"]
        return {x["name"]: int(x["port_id"]) for x in ports}

    def _translate_name_if_necessary(self, value: str) -> str:
        value = super()._translate_name_if_necessary(value)
        return value.replace('.', '_')  # NIKSS uses '_' instead of '.' in fully qualified names

    def translate_interface_to_port(self, intf: str) -> Optional[int]:
        return self._interface_to_port.get(intf)

    def _reset_state_impl(self) -> None:
        _logger.error("'reset_state' is yet to be implemented for NIKSS switches: it is no-op currently")

    def _register_set_impl(self, register_name: str, index: int, value: str) -> None:
        self._run(f"register set pipe {self._pipeline} {register_name} index {index} value {value}")

    def _table_add_impl(self, table_name: str, match_keys: List[str], action_name: str,
                        action_params: List[str]) -> None:
        cmd = f"table add pipe {self._pipeline} {table_name} action name {action_name} key {' '.join(match_keys)}"
        if len(action_params) > 0:
            cmd += f" data {' '.join(action_params)}"
        self._run(cmd)

    def _table_modify_impl(self, table_name: str, match_keys: List[str], action_name: str,
                           action_params: List[str]) -> None:
        cmd = f"table update pipe {self._pipeline} {table_name} action name {action_name} key {' '.join(match_keys)}"
        if len(action_params) > 0:
            cmd += f" data {' '.join(action_params)}"
        self._run(cmd)

    def _table_set_default_impl(self, table_name: str, action_name: str, action_params: List[str]) -> None:
        cmd = f"table default set pipe {self._pipeline} {table_name} action name {action_name}"
        if len(action_params) > 0:
            cmd += f" data {' '.join(action_params)}"
        self._run(cmd)

    def _table_delete_impl(self, table_name: str, match_keys: List[str]) -> None:
        self._run(f"table delete pipe {self._pipeline} {table_name} key {' '.join(match_keys)}")

    def _table_clear_impl(self, table_name: str) -> None:
        # Due to a bug in nikss-ctl, the table clear command doesn't always remove all entries
        # Solution: repeat the clear command until the table is empty
        last_count = -1
        while True:
            # Get the list of currently active keys, where each key is a list of dictionaries
            json_obj = json.loads(self._run(f"table get pipe {self._pipeline} {table_name}"))
            json_keys: List[List[Dict[str, Any]]] = [entry["key"] for entry in json_obj[table_name]["entries"]]

            if len(json_keys) == 0:
                break
            elif len(json_keys) == last_count:
                _logger.error(f"Number of entries in '{table_name}' did not decrease after a delete operation")
                break
            else:
                last_count = len(json_keys)
                self._run(f"table delete pipe {self._pipeline} {table_name}", supress_stderr=True)

    def _multicast_group_create_impl(self, group_id: int, members: List[ApiBridge.MulticastGroupMember]) -> None:
        self._run(f"multicast-group create pipe {self._pipeline} id {group_id}")
        for member in members:
            cmd = (f"multicast-group add-member pipe {self._pipeline} id {group_id}"
                   f" egress-port {member.egress_interface} instance {member.instance_id}")
            self._run(cmd)

    def _clone_session_create_impl(self, session_id: int, members: List[ApiBridge.CloneSessionMember]) -> None:
        self._run(f"clone-session create pipe {self._pipeline} id {session_id}")
        for member in members:
            cmd = (f"clone-session add-member pipe {self._pipeline} id {session_id}"
                   f" egress-port {member.egress_interface} instance {member.instance_id}")
            if member.class_of_service is not None:
                cmd += f" cos {member.class_of_service}"
            if member.truncate_after_packet_length is not None:
                cmd += f" truncate plen_bytes {member.truncate_after_packet_length}"
            self._run(cmd)
