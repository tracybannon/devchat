from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
import hashlib
import math
from typing import Dict, List
from devchat.message import Message
from devchat.utils import unix_to_local_datetime, get_logger, user_id


logger = get_logger(__name__)


@dataclass
class Prompt(ABC):
    """
    A class to represent a prompt and its corresponding responses from the chat API.

    Attributes:
        model (str): The name of the language model.
        user_name (str): The name of the user.
        user_email (str): The email address of the user.
        _new_messages (dict): The messages for the current round of conversation.
        _history_messages (dict): The messages for the history of conversation.
        parent (str): The parent prompt hash.
        references (List[str]): The hashes of the referenced prompts.
        _timestamp (int): The timestamp when the response was created.
        _request_tokens (int): The number of tokens used in the request.
        _response_tokens (int): The number of tokens used in the response.
        _hash (str): The hash of the prompt.
    """

    model: str
    user_name: str
    user_email: str
    _new_messages: Dict = field(default_factory=lambda: {
        Message.INSTRUCT: [],
        'request': None,
        Message.CONTEXT: [],
        'responses': []
    })
    _history_messages: Dict[str, Message] = field(default_factory=lambda: {
        Message.CONTEXT: [],
        Message.CHAT: []
    })
    parent: str = None
    references: List[str] = field(default_factory=list)
    _timestamp: int = None
    _request_tokens: int = 0
    _response_tokens: int = 0
    _hash: str = None

    def _check_complete(self) -> bool:
        """
        Check if the prompt is complete for hashing.

        Returns:
            bool: Whether the prompt is complete.
        """
        if not self.request or not self.responses:
            logger.warning("Incomplete prompt: request = %s, response = %s",
                           self.request, self.responses)
            return False

        if not self._request_tokens or not self._response_tokens:
            logger.warning("Incomplete prompt: request_tokens = %d, response_tokens = %d",
                           self._request_tokens, self._response_tokens)
            return False

        return True

    @property
    def timestamp(self) -> int:
        return self._timestamp

    @property
    def new_context(self) -> List[Message]:
        return self._new_messages[Message.CONTEXT]

    @property
    def request(self) -> Message:
        return self._new_messages['request']

    @property
    def responses(self) -> List[Message]:
        return self._new_messages['responses']

    @property
    def request_tokens(self) -> int:
        return self._request_tokens

    @property
    def response_tokens(self) -> int:
        return self._response_tokens

    @abstractmethod
    def _count_response_tokens(self) -> int:
        """
        Calculate the number of tokens used in the responses.
        """

    @property
    def hash(self) -> str:
        return self._hash

    @property
    @abstractmethod
    def messages(self) -> List[dict]:
        """
        List of messages in the prompt to be sent to the chat API.
        """

    @abstractmethod
    def input_messages(self, messages: List[dict]):
        """
        Input the messages from the chat API to new and history messages.
        The message list should be generated by the `messages` property.

        Args:
            messages (List[dict]): The messages from the chat API.
        """

    @abstractmethod
    def append_new(self, message_type: str, content: str,
                   available_tokens: int = math.inf) -> bool:
        """
        Append a new message provided by the user to this prompt.

        Args:
            message_type (str): The type of the message.
            content (str): The content of the message.
            available_tokens (int): The number of tokens available for the message.

        Returns:
            bool: Whether the message is appended.
        """

    @abstractmethod
    def prepend_history(self, prompt: "Prompt", token_limit: int = math.inf) -> bool:
        """
        Add the prompt to the beginning of the history messages.

        Args:
            prompt(Prompt): The prompt to prepend.
            token_limit (int): The max number of tokens for this prompt.

        Returns:
            bool: Whether the message is prepended.
        """

    @abstractmethod
    def set_request(self, content: str):
        """
        Set the request message for the prompt.

        Args:
            content (str): The request content to set.
        """

    @abstractmethod
    def set_response(self, response_str: str):
        """
        Parse the API response string and set the Prompt object's attributes.

        Args:
            response_str (str): The JSON-formatted response string from the chat API.
        """

    @abstractmethod
    def append_response(self, delta_str: str) -> str:
        """
        Append the content of a streaming response to the existing messages.

        Args:
            delta_str (str): The JSON-formatted delta string from the chat API.

        Returns:
            str: The delta content with index 0. None when the response is over.
        """

    def finalize_hash(self) -> str:
        """
        Calculate and set the hash of the prompt.

        Returns:
            str: The hash of the prompt. None if the prompt is incomplete.
        """
        if not self._check_complete():
            self._hash = None

        if self._hash:
            return self._hash

        self._count_response_tokens()

        data = asdict(self)
        data.pop('_hash')
        string = str(tuple(sorted(data.items())))
        self._hash = hashlib.sha256(string.encode('utf-8')).hexdigest()
        return self._hash

    def formatted_header(self) -> str:
        """Formatted string header of the prompt."""
        formatted_str = f"User: {user_id(self.user_name, self.user_email)[0]}\n"

        local_time = unix_to_local_datetime(self._timestamp)
        formatted_str += f"Date: {local_time.strftime('%a %b %d %H:%M:%S %Y %z')}\n\n"

        return formatted_str

    def formatted_response(self, index: int) -> str:
        """
        Formatted response of the prompt.

        Args:
            index (int): The index of the response to format.

        Returns:
            str: The formatted response string. None if the response is incomplete.
        """
        formatted_str = self.formatted_header()

        if index >= len(self.responses) or not self.responses[index]:
            logger.error("Response index %d is incomplete to format: request = %s, response = %s",
                         index, self.request, self.responses)
            return None

        if self.responses[index].content:
            formatted_str += self.responses[index].content
            formatted_str += "\n\n"

        if self.responses[index].finish_reason == 'function_call':
            formatted_str += self.responses[index].function_call_to_json()
        formatted_str += f"\n\nfinish_reason: {self.responses[index].finish_reason}" + "\n\n"

        formatted_str += f"prompt {self.hash}"

        return formatted_str

    def shortlog(self) -> List[dict]:
        """Generate a shortlog of the prompt."""
        if not self.request or not self.responses:
            raise ValueError("Prompt is incomplete for shortlog.")

        responses = []
        for message in self.responses:
            responses += ((message.content if message.content else "")
                          + message.function_call_to_json())

        return {
            "user": user_id(self.user_name, self.user_email)[0],
            "date": self._timestamp,
            "context": [msg.to_dict() for msg in self.new_context],
            "request": self.request.content,
            "responses": responses,
            "request_tokens": self._request_tokens,
            "response_tokens": self._response_tokens,
            "hash": self.hash,
            "parent": self.parent
        }
