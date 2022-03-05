from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING, Union

from ..exceptions import RedditException

if TYPE_CHECKING:
    from ..client import HTTPClient


class BaseListing(list[Any], ABC):
    """
    Base abstract class for all types of listings returned. Inherits from the `list` type.
    """
    # maximum limit for a single fetch
    # subclasses can overwrite this if needed
    _max_limit = 100

    def __init__(self, client: HTTPClient, method: str, *args, **kwargs):
        self._client = client
        self._method = getattr(client, method)
        self.before = kwargs.pop("before", None)
        self.after = kwargs.pop("after", None)
        self.reverse = kwargs.pop("reverse", False)
        self.limit = kwargs.pop("limit", None)
        try:
            self.count = kwargs.pop("count")
        except KeyError:
            # no 'count' was specified, so we need to assume one
            if self.limit is not None and self.reverse:
                self.count = self.limit
            else:
                self.count = 0
        self._args = args
        self._kwargs = kwargs
        self._initialized = False
        self._iter = None

    def __aiter__(self):
        return self

    def __await__(self):
        return self._initialize().__await__()

    async def _initialize(self):
        if not self._initialized:
            self._initialized = True
            await self._fetch(0)
        return self

    def prev(self):
        """
        Try to fetch the previous page of the listing.

        Returns
        -------
        bool
            `True` if managed to fetch the page, `False` otherwise.

        Raises
        ------
        RedditException
            Raised when trying to operate on an uninitialized listing.
        """
        if not self._initialized:
            raise RedditException("A listing has to be initialized (awaited on) first!")
        return self._fetch(-1)

    def next(self):
        """
        Try to fetch the next page of the listing.

        Returns
        -------
        bool
            `True` if managed to fetch the page, `False` otherwise.

        Raises
        ------
        RedditException
            Raised when trying to operate on an uninitialized listing.
        """
        if not self._initialized:
            raise RedditException("A listing has to be initialized (awaited on) first!")
        return self._fetch(1)

    async def __anext__(self):
        if not self._initialized:
            await self._initialize()
            self._iter = iter(self)
        while True:
            try:
                return next(self._iter)
            except StopIteration:
                # fetch
                if self.reverse:
                    can_continue = await self._fetch(-1)
                else:
                    can_continue = await self._fetch(1)
                # stop if we can't continue
                if not can_continue:
                    raise StopAsyncIteration
                self._iter = iter(self)

    async def _fetch(self, direction: int):
        """
        The main method responsible for fetching data from a listing endpoint.

        Subclasses may overwrite this if they wish to implement custom behavior with handling
        the parameters or data returned, but normally you don't need to do that - overwriting
        `_prepare_params` and `_update_data` should suffice.

        Parameters
        ----------
        direction : int
            Indicates the direction of traversal.
            ``1`` for forward (after), ``-1`` for backward (before).
            ``0`` can be used for initialization (both before and after can be used, as available).

        Returns
        -------
        bool
            `True` if the caller should continue in the direction specified, `False` otherwise.
        """
        # prepare new parameters
        params = {}
        if self.count < 0:
            self.count = 0
        if self.limit is None:
            limit = self._max_limit
        else:
            if direction == -1 or direction == 0 and self.reverse:
                # check if we've reached the beginning of the listing
                if self.count <= 0:
                    return False
                limit = min(self.count, self.limit, self._max_limit)
            elif direction == 1 or direction == 0 and not self.reverse:
                # check if we've reached the end of the listing
                if self.count >= self.limit:
                    return False
                limit = min(self.limit - self.count, self._max_limit)
            else:
                raise RuntimeError("Invalid 'direction' value")
        # return if we can't fetch due to the limit being 0
        if limit <= 0:
            return False
        params["limit"] = limit
        # runs on backward and initialize (-1 or 0)
        if direction != 1:
            # use stored if available
            if self.before is not None:
                params["before"] = self.before
            # if forced to move by the lack of limit,
            # use the first item's fullname for the 'before' parameter
            elif self.limit is None and self:
                index = -1 if self.reverse else 0
                fullname = self[index].fullname
                if fullname:
                    params["before"] = fullname
                else:
                    return False
            # we cannot move anywhere from here
            elif direction != 0:  # ignore initialization
                return False
        # runs on forward and initialize (1 or 0)
        if direction != -1:
            # use stored if available
            if self.after is not None:
                params["after"] = self.after
            # if forced to move by the lack of limit,
            # use the last item's fullname for the 'after' parameter
            elif self.limit is None and self:
                index = 0 if self.reverse else -1
                fullname = self[index].fullname
                if fullname:
                    params["after"] = fullname
                else:
                    return False
            # we cannot move anywhere from here
            elif direction != 0:  # ignore initialization
                return False
        if self.count:
            params["count"] = self.count
        # include additional paremeters if present
        params.update(self._kwargs)
        # fetch the new data
        data = await self._method(*self._args, params=params)
        # forward whatever _update_data returns as the return value
        return await self._update_data(direction, data)

    @abstractmethod
    async def _update_data(self, direction: int, data: Union[list, dict]) -> bool:
        """
        Implemets returned data processing.

        Subclasses should overwrite this method to implement data extraction and all processing
        necessary to fill up the listing appropriately (clear and extend), as well as update
        the 'count', 'before' and 'after' parameters.

        Parameters
        ----------
        direction : int
            See `_fetch`.
        data : Union[list, dict]
            The raw data returned from the endpoint. This can be either a list or a dict,
            depending on the particular endpoint.

        Returns
        -------
        bool
            `True` if we can continue in the direction specified, `False` otherwise.
        """
        raise NotImplementedError
