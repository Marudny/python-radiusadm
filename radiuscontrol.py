import errno
import socket
import struct
import logging
from enum import Enum, auto


class FrChannelType(Enum):
    FR_CHANNEL_STDIN = 0
    FR_CHANNEL_STDOUT = auto()
    FR_CHANNEL_STDERR = auto()
    FR_CHANNEL_CMD_STATUS = auto()
    FR_CHANNEL_INIT_ACK = auto()
    FR_CHANNEL_AUTH_CHALLENGE = auto()
    FR_CHANNEL_AUTH_RESPONSE = auto()
    FR_CHANNEL_WANT_MORE = auto()


class RadiusControl:
    def __init__(self, unix_socket_path: str):
        self.__sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.__sock.connect(unix_socket_path)
        self.__magic_number = 0xf7eead16

    def __lowrite(self, fd: socket.socket, data: bytes) -> int:
        ''' Method for writing '''
        logging.debug("Lowrite: data %s", data)
        total_written = 0
        while total_written < len(data):
            try:
                written = fd.send(data[total_written:])
                if written == 0:
                    return 0  # EOF
                total_written += written
            except socket.herror as e:
                if e.errno == errno.EINTR:
                    continue
                return -1
        return total_written

    def __loread(self, fd: socket.socket, datalen: int = 0) -> bytes:
        ''' Method for reading '''
        data = fd.recv(datalen)
        return data

    def connect(self) -> int:
        magic_bytes = struct.pack('>II', self.__magic_number, 0)
        r = self.__write_to_channel(FrChannelType.FR_CHANNEL_INIT_ACK,
                                    magic_bytes, len(magic_bytes))
        if r <= 0:
            logging.error("Error in socket")
            self.__sock.close()
            return -1
        channel, data = self.__read_from_channel(8)

        if len(data) <= 0:
            logging.error("Empty response")
            self.__sock.close()
            return -1
        if len(data) != 8 or channel != FrChannelType.FR_CHANNEL_INIT_ACK \
                or magic_bytes != data:
            logging.error("Incompatible versions")
            return -1
        return 0

    def run_command(self, command: str) -> int:
        r = self.__write_to_channel(FrChannelType.FR_CHANNEL_STDIN,
                                    str.encode(command), len(command))
        if r <= 0:
            return r

        while True:
            channel, data = self.__read_from_channel(1024)
            if channel == FrChannelType.FR_CHANNEL_STDOUT:
                print(data.decode().strip())
            if channel == FrChannelType.FR_CHANNEL_CMD_STATUS:
                if len(data) < 4:
                    return 1
                else:
                    status = struct.unpack("I", data)
                    return status[0]
            if channel == FrChannelType.FR_CHANNEL_STDERR:
                logging.error(data.decode().strip())
                return -1

    def __write_to_channel(self, channel: FrChannelType, inbuf: bytes,
                           buflen: int) -> int:
        # Create the header
        hdr = struct.pack("!II", channel.value, buflen)
        # Send data
        r = self.__lowrite(self.__sock, hdr)
        if r <= 0:
            return r

        # Write the data directly from the buffer
        r = self.__lowrite(self.__sock, inbuf)
        if r <= 0:
            return r
        return buflen

    def __read_from_channel(self, buflen: int) -> tuple[FrChannelType, bytes]:
        hdr_size = struct.calcsize("!II")
        hdr_data = self.__loread(self.__sock, hdr_size)
        if not hdr_data or len(hdr_data) != hdr_size:
            return (FrChannelType.FR_CHANNEL_STDERR, b'') if hdr_data is None \
                else (FrChannelType.FR_CHANNEL_STDERR, b'')
        channel, data_len = struct.unpack("!II", hdr_data)

        logging.debug("C:", channel, "DL:", data_len)
        data = self.__loread(self.__sock, data_len)

        while data_len > buflen:
            print("DISC")
            discard = min(data_len - buflen, 64)
            junk = self.__loread(self.__sock, discard)
            if not junk or len(junk) != discard:
                break
            data_len -= len(junk)
        return (FrChannelType(channel), data)
