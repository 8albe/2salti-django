from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseOCRProvider(ABC):
    """
    Abstract Base Class for all OCR Providers.
    Defines the contract for document processing and raw response handling.
    """

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Returned the unique identifier for this provider (e.g., 'openai-gpt4o')."""
        pass

    @abstractmethod
    def process_document(self, file_path: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Main entry point for processing a document.
        Should return a dictionary containing extracted data.
        Concrete implementations must also handle saving the raw response
        to the OCRRawResponse model if possible (or delegation to a service).
        """
        pass

    def __str__(self):
        return f"OCRProvider[{self.provider_id}]"
