import logging
from pathlib import Path
from typing import Dict, List, Optional

from p4_api_bridge import ApiBridge

_logger: logging.Logger = logging.getLogger(__name__)


class SimpleSwitchP4RuntimeApiBridge(ApiBridge):
    def __init__(self, switch: str, device_id: int, grpc_port: int,
                 switch_p4rt_path: Path, switch_json_path: Path, interface_to_port: Dict[str, int]) -> None:
        super().__init__(switch)
        self._interface_to_port = interface_to_port
        _logger.debug(f"{self._switch}: Device ID: {device_id}; gRPC port: {grpc_port}")
        _logger.debug(f"{self._switch}: Interfaces: {interface_to_port}")
        _logger.debug(f"{self._switch}: JSON paths: {switch_p4rt_path}; {switch_json_path}")
        from p4utils.utils.sswitch_p4runtime_API import SimpleSwitchP4RuntimeAPI
        self._impl: SimpleSwitchP4RuntimeAPI = SimpleSwitchP4RuntimeAPI(device_id, grpc_port,
                                                                        p4rt_path=str(switch_p4rt_path),
                                                                        json_path=str(switch_json_path))

    def translate_interface_to_port(self, intf: str) -> Optional[int]:
        return self._interface_to_port.get(intf)

    def _reset_state_impl(self) -> None:
        self._impl.reset_state()
        _logger.error("'reset_state' is not reliable for P4Runtime switches according to the documentation")

    def _register_set_impl(self, register_name: str, index: int, value: str) -> None:
        raise RuntimeError("P4Runtime does not support direct register writes")

    def _table_add_impl(self, table_name: str, match_keys: List[str], action_name: str,
                        action_params: List[str]) -> None:
        self._impl.table_add(table_name, action_name, match_keys, action_params)

    def _table_modify_impl(self, table_name: str, match_keys: List[str], action_name: str,
                           action_params: List[str]) -> None:
        self._impl.table_modify_match(table_name, action_name, match_keys, action_params)

    def _table_set_default_impl(self, table_name: str, action_name: str, action_params: List[str]) -> None:
        self._impl.table_set_default(table_name, action_name, action_params)

    def _table_delete_impl(self, table_name: str, match_keys: List[str]) -> None:
        self._impl.table_delete_match(table_name, match_keys)

    def _table_clear_impl(self, table_name: str) -> None:
        self._impl.table_clear(table_name)

    def _multicast_group_create_impl(self, group_id: int, members: List[ApiBridge.MulticastGroupMember]) -> None:
        self._impl.mc_mgrp_create(group_id, [m.egress_interface for m in members], [m.instance_id for m in members])

    def _clone_session_create_impl(self, session_id: int, members: List[ApiBridge.CloneSessionMember]) -> None:
        # Validate that each "class of service" and "truncate after packet length" is the same for all members
        cos, truncate = members[0].class_of_service, members[0].truncate_after_packet_length
        if any(m.class_of_service != cos or m.truncate_after_packet_length != truncate for m in members):
            raise ValueError("All clone session members must have the same class of service and truncation length"
                             " when the P4Runtime API is used")

        cos = cos if cos is not None else 0
        truncate = truncate if truncate is not None else 0
        self._impl.cs_create(session_id, [m.egress_interface for m in members],
                             [m.instance_id for m in members], cos, truncate)
