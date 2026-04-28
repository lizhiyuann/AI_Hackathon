"""SSH远程执行器"""
from typing import Optional
from src.connector.local import ExecutionResult
from src.utils.logger import log


class RemoteExecutor:
    """SSH远程命令执行器"""

    def __init__(self, host: str, port: int = 22, username: str = "", key_path: str = "", password: str = ""):
        self.host = host
        self.port = port
        self.username = username
        self.key_path = key_path
        self.password = password
        self._client = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    @staticmethod
    def _decode_output(data: bytes) -> str:
        """尝试多种编码解码输出，兼容中文服务器"""
        if not data:
            return ""
        for encoding in ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin-1']:
            try:
                return data.decode(encoding).strip()
            except (UnicodeDecodeError, LookupError):
                continue
        return data.decode('utf-8', errors='replace').strip()

    def connect(self):
        """建立SSH连接"""
        try:
            import paramiko
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs = {
                "hostname": self.host,
                "port": self.port,
                "username": self.username,
                "timeout": 15,
                "banner_timeout": 15,
            }

            if self.key_path:
                connect_kwargs["key_filename"] = self.key_path
            elif self.password:
                connect_kwargs["password"] = self.password

            self._client.connect(**connect_kwargs)
            log.info(f"SSH连接成功: {self.host}:{self.port}")
        except Exception as e:
            # 连接失败时清理 _client，避免后续在残废连接上执行命令
            if self._client:
                try:
                    self._client.close()
                except Exception:
                    pass
            self._client = None
            log.error(f"SSH连接失败: {e}")
            raise

    def execute(self, command: str, timeout: Optional[int] = 30) -> ExecutionResult:
        """执行远程命令"""
        try:
            if not self._client:
                self.connect()

            if not self._client:
                return ExecutionResult(
                    success=False, output="",
                    error="SSH 连接未建立",
                    return_code=-1,
                )

            stdin, stdout, stderr = self._client.exec_command(command, timeout=timeout)
            output = self._decode_output(stdout.read())
            error = self._decode_output(stderr.read())
            return_code = stdout.channel.recv_exit_status()

            return ExecutionResult(
                success=return_code == 0,
                output=output,
                error=error,
                return_code=return_code,
            )
        except Exception as e:
            # 命令执行失败时清理连接，下次调用会自动重连
            try:
                if self._client:
                    self._client.close()
            except Exception:
                pass
            self._client = None
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                return_code=-1,
            )

    def close(self):
        """关闭连接"""
        if self._client:
            self._client.close()
            self._client = None
