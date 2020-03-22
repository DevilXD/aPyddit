from __future__ import annotations

from typing import TYPE_CHECKING, Union, List, Optional

from .base import Thing
from .asset import Asset
from .mixins import Created, Votable
from .partials import (
    PartialUser,
    PartialPost,
    PartialSubreddit,
)

if TYPE_CHECKING:
    from .http import HTTPClient
    from .base import ClientBase


ThingID = str


def get_thing(caller: "ClientBase", thing_data: dict):
    kind = thing_data["kind"]
    if kind == "t1":
        return Comment(caller._client, thing_data)
    elif kind == "t2":
        return User(caller._client, thing_data)
    elif kind == "t3":
        return Post(caller._client, thing_data)
    elif kind == "t4":
        return Message(caller._client, thing_data)
    elif kind == "t5":
        return Subreddit(caller._client, thing_data)
    # elif kind == "t6":
    #     return Award(caller._client, thing_data)
    elif kind == "more":
        return More(caller._client, thing_data)
    raise TypeError


class User(PartialUser, Thing, Created):
    def __init__(self, client: "HTTPClient", user_data: dict):
        Thing.__init__(self, client, user_data)
        data = user_data["data"]
        Created.__init__(self, data)
        self.data = data


class Post(PartialPost, Thing, Created, Votable):
    def __init__(
        self,
        client: "HTTPClient",
        post_data: dict,
        comments_data: Optional[List[dict]] = None,
    ):
        Thing.__init__(self, client, post_data)
        data = post_data["data"]
        Created.__init__(self, data)
        Votable.__init__(self, data)
        self.data = data
        self._comments_data = comments_data
        self.title = data["title"]
        self.url = data["url"]
        self.text = data["selftext"]
        self.subreddit = PartialSubreddit(self._client, data["subreddit"])
        self.permalink = data["permalink"]
        self.send_replies = data["send_replies"]
        self.quarantined = data["quarantine"]
        self.stickied = data["stickied"]
        self.spoiler = data["spoiler"]
        self.visited = data["visited"]
        self.pinned = data["pinned"]
        self.nsfw = data["over_18"]
        self.saved = data["saved"]

    def __repr__(self) -> str:
        return "Post({0.id}, {0.title})".format(self)

    def comments(self):
        from .comment_tree import CommentTree  # cyclic imports
        return CommentTree(self, self._comments_data)


class Comment(Thing, Created, Votable):
    def __init__(
        self,
        client: "HTTPClient",
        comment_data: dict,
    ):
        Thing.__init__(self, client, comment_data)
        data = comment_data["data"]
        Created.__init__(self, data)
        Votable.__init__(self, data)
        self.data = data
        # Post and Parent
        self._parent = None  # overwritten in the classmethods
        self._post = None  # overwritten in the classmethods
        self._parent_id = data["parent_id"]
        self._post_id = data["link_id"]
        # Bools:
        self.saved = data["saved"]
        self.content = data["body"]
        self.edited = data["edited"]  # TODO: add a timestamp to this
        self.locked = data["locked"]
        self.archived = data["archived"]
        self.stickied = data["stickied"]
        self.collapsed = data["collapsed"]
        self.score_hidden = data["score_hidden"]
        self.send_replies = data["send_replies"]
        # Replies:
        from .comment_tree import CommentTree  # cyclic imports
        if data["replies"]:
            self.replies = CommentTree.from_post(self, data["replies"]["data"]["children"])
        else:
            self.replies = CommentTree.from_post(self, [])
        # if data["replies"]:
        #     for thing_data in data["replies"]["data"]["children"]:
        #         if thing_data["kind"] == "t1":
        #             self.replies.append(
        #                 Comment(self.post, self, thing_data)
        #             )
        #         elif thing_data["kind"] == "more":
        #             self.replies.append(
        #                 More(self.post, self, thing_data)
        #             )
        # TODO:
        # self.author = ...

    async def parent(self) -> Union[Post, "Comment"]:
        """
        Retrieves the parent of this comment.

        Returns
        -------
        Union[Post, Comment]
        """
        if self._parent is None:
            if self._parent_id.startswith("t3"):
                parent_data = await self._client.get_post(self._parent_id)
                self._parent = Post(self._client, parent_data)
            elif self._parent_id.startswith("t1"):
                parent_data = await self._client.get_comment(self._post_id, self._parent_id)
                self._parent = Comment(self._client, parent_data)
        return self._parent

    async def post(self) -> Post:
        """
        Retrieves the post this comment belongs to.
        """
        if self._post is None:
            post_data = await self._client.get_post(self._post_id)
            self._post = Post(self._client, post_data)
        return self._post

    @classmethod
    def from_post(cls, post: Post, comment_data: dict):
        inst = cls(post._client, comment_data)
        inst._post = post
        inst._parent = post
        return inst

    @classmethod
    def from_comment(cls, comment: "Comment", comment_data: dict):
        inst = cls(comment._client, comment_data)
        inst._post = comment._post
        inst._parent = comment
        return inst

    @classmethod
    def from_listing(
        cls,
        sub: Union[PartialSubreddit, "Subreddit"],
        comment_data: dict,
    ):
        return cls(sub._client, comment_data)


class Message(Thing, Created):
    def __init__(self, client: "HTTPClient", msg_data: dict):
        Thing.__init__(self, client, msg_data)
        data = msg_data["data"]
        Created.__init__(self, data)
        self.data = data


class Subreddit(PartialSubreddit, Thing, Created):
    def __init__(self, client: "HTTPClient", sub_data: dict):
        Thing.__init__(self, client, sub_data)
        data = sub_data["data"]
        self.data = data
        self.display_name = data["display_name"]
        self.icon = Asset(self._client, data["icon_img"], data["icon_size"])
        self.banner = Asset(self._client, data["banner_img"], data["banner_size"])
        self.header = Asset(self._client, data["header_img"], data["header_size"])
        self.users_active = data["accounts_active"]
        self.subscribers = data["subscribers"]
        self.sidebar = data["description"]
        self.description = data["public_description"]
        self.language = data["lang"]
        self.nsfw = data["over18"]
        self.quarantined = data["quarantine"]


class More(Thing):
    def __init__(
        self,
        parent: Union[Post, Comment],
        more_data: dict,
    ):
        Thing.__init__(self, parent._client, more_data)
        data = more_data["data"]
        if type(parent) == Post:
            self.post = parent
        else:
            self.post = parent.post
        self.parent = parent
        self.children = data["children"]
        self.count = data["count"]

    def __await__(self):
        return self._fetch().__await__()

    async def _fetch(self) -> List[Comment]:
        if self.children:
            more = await self._client.get_more_children(self.post.id, self.children)
        elif self.id == '_':
            # special case for "Continue the thread" buttons
            more = await self._client.get_comment(self.post.id, self.parent.id)
            # we're interested in the replies only
            more = more["data"]["replies"]["data"]["children"]
        else:
            return []
        comments = []
        for o in more:
            kind = o.get("kind")
            if kind == "t1":
                comments.append(Comment(self.parent, o))
            elif kind == "more":
                comments.append(More(self.parent, o))
        return comments
        # return [Comment(self.post, self.parent, comment_data) for comment_data in comments]
