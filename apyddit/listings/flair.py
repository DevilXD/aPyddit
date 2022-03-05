from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from .base import BaseListing

if TYPE_CHECKING:
    from ..models import Subreddit  # noqa
    from ..client import HTTPClient
    from ..partials import PartialSubreddit, PartialUser, Flair  # noqa


class FullnameWrapper(NamedTuple):
    user: PartialUser
    flair: Flair

    @property
    def fullname(self):
        # partial users don't have a fullname, so we need to spoof None here
        return None

    def __repr__(self):
        return "({}, {})".format(*self)


# TODO: Test this and update the class docstring
class FlairListing(BaseListing):
    """
    Base abstract class for all types of listings returned. Inherits from the `list` type.
    """
    _max_limit = 1000

    def __init__(
        self,
        client: HTTPClient,
        subreddit: PartialSubreddit | Subreddit,
        *args,
        **kwargs,
    ):
        super().__init__(client, "get_subreddit_flair_list", *args, **kwargs)
        self._subreddit = subreddit
        self._args += (subreddit.display_name,)

    async def _update_data(self, direction: int, data) -> bool:
        # update the 'count' parameter
        dist = len(data["users"])
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
        self.before = data.get("prev")
        self.after = data.get("next")
        # update the internal list of things, if we've got any
        if dist:
            from ..partials import PartialUser, Flair
            self.clear()
            # List[Tuple[PartialUser, Flair]]
            self.extend(
                FullnameWrapper(
                    PartialUser(self._client, flair_data["user"]),
                    Flair(
                        self._subreddit, flair_data["flair_css_class"], flair_data["flair_text"]
                    ),
                )
                for flair_data in data["users"]
            )
            return True
        # we've got an empty response, so you probably shouldn't continue
        return False
