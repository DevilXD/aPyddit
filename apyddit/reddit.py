from typing import Union

from .http import HTTPClient
from .partials import (
    # Thing,
    # Comment,
    PartialUser,
    PartialPost,
    # Message,
    PartialSubreddit,
    # Award",
)
from .models import (
    # Thing,
    # Comment,
    User,
    Post,
    Subreddit,
    # Award",
)


class Reddit:
    """
    The main class for the Reddit API access.
    """
    def __init__(
        self,
        user_agent: str,
        client_id: str,
        client_secret: str,
        username: str,
        password: str,
    ):
        self.client_id = client_id
        self._client = HTTPClient(user_agent, client_id, client_secret, username, password)
        self.request = self._client.request  # forward the request method

    def close(self):
        return self._client.close()

    def subreddit(self, name: str) -> Union[PartialSubreddit, Subreddit]:
        """
        Returns a model representing a Subreddit.

        `await`ing this method returns a full `Subreddit` model, with all attributes set.

        Parameters
        ----------
        name : str
            Name of the subreddit you want to get, without the '/r/' prefix.

        Returns
        -------
        Union[PartialSubreddit, Subreddit]
            An object representing the Subreddit requested.
        """
        return PartialSubreddit(self._client, name)

    def user(self, username: str) -> Union[PartialUser, User]:
        """
        Return a model representing a Reddit User.

        `await`ing this method returns a full `User` model, with all attributes set.

        Parameters
        ----------
        username : str
            The username of the User you want to get, without the '/u/' prefix.

        Returns
        -------
        Union[PartialUser, User]
            An object representing the User requested.
        """
        return PartialUser(self._client, username)

    def post(self, post_id: str) -> Union[PartialPost, Post]:
        return PartialPost(self._client, post_id)
