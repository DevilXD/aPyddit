import aiohttp
from typing import Optional, Union


class RedditException(Exception):
    """
    Base exception class for Reddit API.
    """
    pass


class UnsupportedTokenType(RedditException):
    """
    OAuth2 Token request returned unsupported token type.
    """
    def __init__(self, token_type):
        super().__init__(f"Token type `{token_type}` is not supported")


class HTTPException(RedditException):
    """Exception that's thrown when an HTTP request operation fails.

    Attributes
    ----------
    response: aiohttp.ClientResponse
        The response of the failed HTTP request.
    status: int
        The status code of the HTTP request.
    data: Optional[dict]
        The response data, if available.
    """

    def __init__(self, response: aiohttp.ClientResponse, data: Optional[Union[dict, str]] = None):
        self.response = response
        self.status = response.status
        self.data = data
        super().__init__(f"{self.response.reason} (status code: {self.status}): {self.data}")
