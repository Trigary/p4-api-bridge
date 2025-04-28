####################################
# Server side of a Remote BF Shell #
####################################
# This script allows a remote client to execute commands within a Tofino BF Runtime shell.
# Sometimes this approach is necessary to avoid the limitations of complex scripts running directly within the shell.


import json
import os


class Container:
    """
    A container class/namespace. It is required because the interpreter doesn't handle globals well.
    The solution was to put everything in a class, instead of having functions in the global namespace.
    """

    def _read_exactly_n_bytes(self, sock, n: int) -> bytes:
        """Reads exactly n bytes from the socket."""
        buffer = bytearray(n)
        view = memoryview(buffer)
        total_read = 0
        while total_read != n:
            just_read = sock.recv_into(view[total_read:], n - total_read)
            total_read += just_read
            if just_read == 0:
                return b''
        return buffer

    def _read_string(self, sock) -> str:
        """Reads a string (e.g. a command) from the socket."""
        cmd = ''
        cmd_length = self._read_exactly_n_bytes(sock, 4)
        if cmd_length != b'':
            cmd = self._read_exactly_n_bytes(sock, int.from_bytes(cmd_length, byteorder='big')).decode()
        return cmd  # Empty value is returned if either the 1st or the 2nd read failed

    def _handle_command(self, program_name: str, cmd: str) -> None:
        """Handles the specified command, potentially throwing an exception."""
        exec('p4 = bfrt.%s.pipeline ; %s' % (program_name, cmd))

    def _send_string(self, sock, msg: str) -> None:
        """Writes the specified string (e.g. an acknowledgement) to the socket."""
        msg = msg.encode()
        msg_length = len(msg).to_bytes(4, byteorder='big')
        sock.sendall(msg_length + msg)

    def _handle_connection(self, sock) -> None:
        """Handles a connection, executing the received commands until the connection is closed."""

        print('Connection established, receiving configuration...')
        config_json_string = self._read_string(sock)
        if len(config_json_string) == 0:
            print('Unable to read configuration, closing connection')
            return

        print('Configuration received: %s' % config_json_string)
        config_json = json.loads(config_json_string)
        program_name = config_json['program_name']
        enable_acknowledgments = config_json['enable_acknowledgments']

        print('Clearing pipeline...')
        # noinspection PyBroadException
        try:
            exec('bfrt.batch_end()')  # In case there is a batch in progress
        except Exception:
            pass
        exec('bfrt.%s.pipeline.clear()' % program_name)

        while True:
            print("Waiting for a command...")
            cmd = self._read_string(sock)
            if len(cmd) == 0:
                print('Connection closed by remote client')
                return

            print("Received command: %s" % cmd)
            self._handle_command(program_name, cmd)
            if enable_acknowledgments:
                self._send_string(sock, 'OK')

    def main(self, port: int, allow_reconnect: bool = False) -> None:
        """
        Main entry point of the server.

        :param port: port to listen on
        :param allow_reconnect: whether the server should wait for additional connections after the first one is closed.
        Use of this is discouraged, as interrupts don't seem to work properly, leaving no way to gracefully close this
        script when this option is enabled.
        """
        print('Importing socket module...')
        import socket

        print('Opening socket...')
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
            print('Configuring socket...')
            server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_sock.bind(('localhost', port))
            server_sock.listen(10)

            while True:
                print("Waiting for a connection on port %d..." % port)
                sock, sock_address = server_sock.accept()
                print("Connection from %s" % str(sock_address))
                with sock:
                    self._handle_connection(sock)
                if not allow_reconnect:
                    return


print("Current process PID: ", os.getpid())
print('Executing main function...')
Container().main(port=52000)
print('Exiting...')
