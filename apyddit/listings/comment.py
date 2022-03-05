from __future__ import annotations

from typing import TYPE_CHECKING

from .base import BaseListing

if TYPE_CHECKING:
    from ..utils import JsonType
    from ..models import Subreddit
    from ..partials import PartialSubreddit


# TODO: Update the class docstring
class CommentListing(BaseListing):
    """
    Base abstract class for all types of listings returned. Inherits from the `list` type.
    """
    def __init__(
        self,
        subreddit: PartialSubreddit | Subreddit,
        *args,
        **kwargs,
    ):
        super().__init__(subreddit._client, "get_subreddit_comments", *args, **kwargs)
        self._sub = subreddit
        self._args += (subreddit.display_name,)

    async def _update_data(self, direction: int, data: JsonType) -> bool:
        data = data["data"]
        # update the 'count' parameter
        dist = data.get("dist") or 0
        if direction == 1:
            self.count += dist
        elif direction == -1:
            self.count -= dist
        else:
            if self.reverse:
                self.count -= dist
            else:
                self.count += dist
        # update the 'before' and 'after' for the next request
        self.before = data.get("before")
        self.after = data.get("after")
        # update the internal list of things, if we've got any
        if data["children"]:
            from ..models import More, Comment  # cyclic imports
            children = reversed(data["children"]) if self.reverse else iter(data["children"])
            self.clear()
            for thing_data in children:
                kind = thing_data["kind"]
                if kind == "t1":
                    self.append(Comment.from_listing(self._sub, thing_data))
                elif kind == "more":
                    self.append(More.from_listing(self._sub, thing_data))
            return True
        # we've got an empty response, so you probably shouldn't continue
        return False
