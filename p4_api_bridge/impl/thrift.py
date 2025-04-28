import logging
from typing import Dict, List, Optional

from p4_api_bridge import ApiBridge

_logger: logging.Logger = logging.getLogger(__name__)


class SimpleSwitchThriftApiBridge(ApiBridge):
    def __init__(self, switch: str, thrift_port: int, interface_to_port: Dict[str, int]) -> None:
        super().__init__(switch)
        self._interface_to_port = interface_to_port
        _logger.debug(f"{self._switch}: Thrift port: {thrift_port}")
        _logger.debug(f"{self._switch}: Interfaces: {interface_to_port}")
        from p4utils.utils.sswitch_thrift_API import SimpleSwitchThriftAPI
        self._impl: SimpleSwitchThriftAPI = SimpleSwitchThriftAPI(thrift_port)

    def translate_interface_to_port(self, intf: str) -> Optional[int]:
        return self._interface_to_port.get(intf)

    def _reset_state_impl(self) -> None:
        self._impl.reset_state()

    def _register_set_impl(self, register_name: str, index: int, value: str) -> None:
        self._impl.register_write(register_name, index, int(value))

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
        self._impl.mc_mgrp_create(group_id)
        for member in members:
            node = self._impl.mc_node_create(member.instance_id, [member.egress_interface])
            self._impl.mc_node_associate(group_id, node)

    def _clone_session_create_impl(self, session_id: int, members: List[ApiBridge.CloneSessionMember]) -> None:
        raise NotImplementedError("Clone (mirroring) sessions are implemented in a unique way in the Thrift API: "
                                  "they require a multicast session, therefore this method is not yet implemented")
