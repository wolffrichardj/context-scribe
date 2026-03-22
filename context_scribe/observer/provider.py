from dataclasses import dataclass
from datetime import datetime
from typing import Iterator, Optional, Protocol


@dataclass
class Interaction:
    timestamp: datetime
    role: str  # "user" or "agent"
    content: str
    metadata: Optional[dict] = None


class BaseProvider(Protocol):
    """Abstract interface for all log providers."""
    
    def watch(self) -> Iterator[Interaction]:
        """
        Continuously yields new interactions as they are detected.
        This is a blocking generator that yields Interaction objects.
        """
        ...
