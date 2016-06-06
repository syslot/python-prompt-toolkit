from .enums import IncrementalSearchDirection
from .filters import to_simple_filter
from .buffer import Buffer

__all__ = (
    'SearchState',
)


class SearchState(object):
    """
    A search 'query'.
    """
    __slots__ = ('search_buffer', 'direction', 'ignore_case')

    def __init__(self, search_buffer, #text='',
                 direction=IncrementalSearchDirection.FORWARD,
                 ignore_case=False):
        assert isinstance(search_buffer, Buffer)
        ignore_case = to_simple_filter(ignore_case)

        self.search_buffer = search_buffer
        self.direction = direction
        self.ignore_case = ignore_case

    def __repr__(self):
        return '%s(%r, direction=%r, ignore_case=%r)' % (
            self.__class__.__name__, self.text, self.direction, self.ignore_case)

    @property
    def text(self):
        " The search string. "
        return self.search_buffer.text

    def __invert__(self):
        """
        Create a new SearchState where backwards becomes forwards and the other
        way around.
        """
        # TODO: add an invert() method that changse the direction in place.
        raise Error('.......')

#        if self.direction == IncrementalSearchDirection.BACKWARD:
#            direction = IncrementalSearchDirection.FORWARD
#        else:
#            direction = IncrementalSearchDirection.BACKWARD
#
#        return SearchState(text=self.text, direction=direction, ignore_case=self.ignore_case)
