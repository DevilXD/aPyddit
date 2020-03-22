import io
import os
from datetime import datetime
from typing import TYPE_CHECKING, Optional, Union, List

from .base import PartialNameThing, PartialIDThing
from .listings import Listing, FlairListing, CommentListing

if TYPE_CHECKING:
    from .http import HTTPClient
    from .models import (
        User,
        Post,
        Subreddit,
    )


class PartialSubreddit(PartialNameThing):
    def __init__(self, client: "HTTPClient", subreddit_name: str):
        super().__init__(client, "t5", subreddit_name)

    async def _upgrade(self) -> "Subreddit":
        """
        Upgrades this object to a full Subreddit object, bearing all subreddit information.
        """
        thing_data = await self._client.get_subreddit(self.display_name)
        from .models import Subreddit  # cyclic imports
        return Subreddit(self._client, thing_data)

    ##################################################
    # Listings
    ##################################################

    def front_page(self, **kwargs) -> Listing:
        """
        Returns a `Listing` for the subreddit's front page.

        Returns
        -------
        Listing
            Listing that contains all posts from the front page.
        """
        return Listing(self._client, "get_front_page", self.display_name, **kwargs)

    def new(self, **kwargs) -> Listing:
        """
        Returns a `Listing` for the subreddit's new submissions.

        Returns
        -------
        Listing
            Listing that contains all posts from the new page.
        """
        return Listing(self._client, "get_new", self.display_name, **kwargs)

    def rising(self, **kwargs) -> Listing:
        """
        Returns a `Listing` for the subreddit's rising submissions.

        Returns
        -------
        Listing
            Listing that contains all posts from the rising page.
        """
        return Listing(self._client, "get_rising", self.display_name, **kwargs)

    def controversial(self, **kwargs) -> Listing:
        """
        Returns a `Listing` for the subreddit's controversial submissions.

        Returns
        -------
        Listing
            Listing that contains all posts from the controversial page.
        """
        return Listing(self._client, "get_controversial", self.display_name, **kwargs)

    def top(self, span: str = "all", **kwargs) -> Listing:
        """
        Returns a `Listing` for the subreddit's top submissions.

        Returns
        -------
        Listing
            Listing that contains all posts from the top page.
        """
        kwargs["t"] = span
        return Listing(self._client, "get_top", self.display_name, **kwargs)

    def flairs(self, **kwargs) -> FlairListing:
        return FlairListing(self._client, self, **kwargs)

    def comments(self, **kwargs) -> CommentListing:
        return CommentListing(self, **kwargs)

    # async def settings(self):
    #     data = await self._client.get_subreddit_settings

    # async def rules(self):
    #     data = await self._client.get_subreddit_rules

    async def traffic(self):
        data = await self._client.get_subreddit_traffic(self.display_name)
        return data

    def mutes(self, **kwargs):
        return Listing(self._client, "get_subreddit_mutes", self.display_name, **kwargs)

    def bans(self, **kwargs):
        return Listing(self._client, "get_subreddit_bans", self.display_name, **kwargs)

    async def moderators(self) -> List["Moderator"]:
        data = await self._client.get_subreddit_moderators(self.display_name)
        return [Moderator(self._client, self, mod_data) for mod_data in data["data"]["children"]]

    def contributors(self, **kwargs):
        return Listing(
            self._client, self._client.get_subreddit_contributors, self.display_name, **kwargs
        )

    def wiki_contributors(self, **kwargs):
        return Listing(
            self._client, self._client.get_subreddit_wiki_contributors, self.display_name, **kwargs
        )

    def wiki_bans(self, **kwargs):
        return Listing(
            self._client, self._client.get_subreddit_wiki_bans, self.display_name, **kwargs
        )

    async def upload_image(
        self,
        file: Union[bytes, io.IOBase, str, os.PathLike],
        upload_type: Optional[str] = None,
        *,
        filename: Optional[str] = None,
    ):
        """
        Uploads an image to the subreddit.

        Parameters
        ----------
        file : Union[bytes, io.IOBase, str, os.PathLike]
            The file to upload, in a form of raw bytes, a path, or an already opened file pointer.
        upload_type : Optional[str]
            The type of the image being uploaded.\n
            This should be either:\n
            • "img" for a stylesheet image\n
            • "banner" for subreddit banner\n
            • "icon" for subreddit icon\n
            • "header" for subreddit header
        filename : Optional[str]
            Can be used to change the name the file is being uploaded under.\n
            Defaults to the original filename.

        Returns
        -------
        bool
            `True` if the upload was successful, `False` otherwise.
        """
        data = await self._client.upload_subreddit_image(
            self.display_name, file, upload_type, filename=filename
        )
        return not bool(data["errors"])


class PartialUser(PartialNameThing):
    def __init__(self, client: "HTTPClient", username: str):
        super().__init__(client, "t2", username)

    async def _upgrade(self) -> "User":
        """
        Upgrades this object to a full User object, bearing all user information.
        """
        thing_data = await self._client.get_user(self.display_name)
        from .models import User  # cyclic imports
        return User(self._client, thing_data)


class PartialPost(PartialIDThing):
    def __init__(self, client, post_id: str):
        super().__init__(client, "t3", post_id)

    async def _upgrade(self) -> "Post":
        from .models import Post
        data = await self._client.get_post(self.id)
        # this takes care of the initial comments as well
        return Post(self._client, *data)


class Flair:
    def __init__(self, subreddit: Union[PartialSubreddit, "Subreddit"], css_class: str, text: str):
        self.subreddit = subreddit
        self.css_class = css_class
        self.text = text


class Moderator(PartialUser):
    def __init__(
        self, client: "HTTPClient", subreddit: Union[PartialSubreddit, "Subreddit"], data: dict
    ):
        PartialUser.__init__(self, client, data["name"])
        self.subreddit = subreddit
        self.since = datetime.fromtimestamp(data["date"])
        self.flair = Flair(subreddit, data["author_flair_css_class"], data["author_flair_text"])
        self.permissions = data["mod_permissions"]
