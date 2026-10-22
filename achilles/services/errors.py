"""Erros públicos estáveis, sem detalhes sensíveis do navegador."""

from typing import Any, Dict, Optional


class ServiceError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        retryable: bool = False,
        recovery: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.recovery = recovery
        self.operation_id: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        result = {"code": self.code, "message": str(self), "retryable": self.retryable}
        if self.recovery:
            result["recovery"] = self.recovery
        if self.operation_id:
            result["operation_id"] = self.operation_id
        return result
