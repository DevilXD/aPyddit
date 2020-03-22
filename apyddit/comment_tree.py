from math import inf
from collections import deque
from abc import ABC, abstractmethod
from typing import Union, List, Optional

from .base import ClientBase
from .models import More, Comment, Post


class CommentTree(ClientBase, list):
    def __init__(self, parent: Union[Post, Comment], comments_data: Optional[List[dict]]):
        super().__init__(parent._client)
        if type(parent) == Post:
            self._post = parent
        else:
            self._post = parent.post
        self._parent = parent
        if comments_data is None:
            self._initialized = False
        else:
            self._fill_data(comments_data)
            self._initialized = True

    def __await__(self):
        return self._initialize().__await__()

    async def _initialize(self):
        if not self._initialized:
            data = await self._client.get_post(self._post.id, limit=500)
            self._fill_data(data[1])  # second ones are comments
            self._initialized = True
        return self

    def _fill_data(self, comments_data: List[dict]):
        for thing_data in comments_data:
            kind = thing_data["kind"]
            # Object(parent, data)
            if kind == "t1":
                self.append(Comment(self._parent, thing_data))
            elif kind == "more":
                self.append(More(self._parent, thing_data))

    def __aiter__(self):
        return DepthFirstCommentIterator(self)

    def depth_first(self, **kwargs):
        return DepthFirstCommentIterator(self, **kwargs)

    def breadth_first(self, **kwargs):
        return BreadthFirstCommentIterator(self, **kwargs)

    @classmethod
    def from_post(cls, post: Post, comments_data: List[dict]):
        return cls(post, comments_data)


class _BacktrackableTreeIterator:

    # default stubs
    remove = lambda: None
    extend = lambda: None

    def __init__(self, tree: CommentTree):
        self._tree = tree
        # forward the 'remove' and 'extend' list methods
        self.remove = self._tree.remove
        self.extend = self._tree.extend
        self._i = 0

    def __iter__(self):
        return self

    def __next__(self):
        try:
            item = self._tree[self._i]
        except IndexError:
            raise StopIteration
        self._i += 1
        return item

    def restart(self):
        self._i = 0

    def backtrack(self, amount: int = 1):
        self._i -= amount


class CommentIterator(ClientBase, ABC):
    def __init__(self, tree: CommentTree, *, depth: int = inf):
        super().__init__(tree._client)
        self._tree = tree
        self._queue = deque()
        self._current = _BacktrackableTreeIterator(self._tree)
        # Iterator settings
        self._max_depth = depth

    def __aiter__(self):
        return self

    async def __anext__(self):
        while True:
            try:
                c = next(self._current)
            except StopIteration:
                if self._queue:
                    self._current = self._queue.pop()
                    continue
                raise StopAsyncIteration
            if type(c) == Comment:
                self._handle_replies(c.replies)
                return c
            else:
                if c.depth < self._max_depth:
                    m = await c                # await on the 'More' object to obtain more comments
                    self._current.remove(c)    # remove the 'More' object from the original list
                    self._current.backtrack()  # back off one step of the iteration
                    self._current.extend(m)    # add the fetched comments to the current list

    @abstractmethod
    async def _handle_replies(self):
        raise NotImplementedError


class DepthFirstCommentIterator(CommentIterator):
    def __init__(self, tree: CommentTree, **kwargs):
        super().__init__(tree, **kwargs)

    def _handle_replies(self, replies: List[Union[Comment, More]]):
        if replies and len(self._queue) < self._max_depth:
            self._queue.append(self._current)
            self._current = _BacktrackableTreeIterator(replies)


class BreadthFirstCommentIterator(CommentIterator):
    def __init__(self, tree: CommentTree, **kwargs):
        super().__init__(tree, **kwargs)

    def _handle_replies(self, replies: List[Union[Comment, More]]):
        if replies and len(self._queue) < self._max_depth:
            self._queue.appendleft(_BacktrackableTreeIterator(replies))
