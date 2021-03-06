
import typing as tp

import numpy as np


from static_frame.core.container import ContainerBase
from static_frame.core.display import Display
from static_frame.core.display import DisplayActive
from static_frame.core.display import DisplayHeader
from static_frame.core.display_config import DisplayConfig
from static_frame.core.doc_str import doc_inject
from static_frame.core.exception import ErrorInitBus
from static_frame.core.frame import Frame
from static_frame.core.node_selector import InterfaceGetItem
from static_frame.core.series import Series
from static_frame.core.store import Store
from static_frame.core.store import StoreConfigMap
from static_frame.core.store import StoreConfigMapInitializer
from static_frame.core.store_client_mixin import StoreClientMixin
from static_frame.core.util import DTYPE_BOOL
from static_frame.core.util import DTYPE_FLOAT_DEFAULT
from static_frame.core.util import DTYPE_OBJECT
from static_frame.core.util import GetItemKeyType
from static_frame.core.util import NameType
from static_frame.core.util import NULL_SLICE
from static_frame.core.util import INT_TYPES

#-------------------------------------------------------------------------------
class FrameDeferredMeta(type):
    def __repr__(cls) -> str:
        return f'<{cls.__name__}>'

class FrameDeferred(metaclass=FrameDeferredMeta):
    '''
    Token placeholder for :obj:`Frame` not yet loaded.
    '''

#-------------------------------------------------------------------------------
class Bus(ContainerBase, StoreClientMixin): # not a ContainerOperand
    '''
    A lazy, randomly-accessible container of :obj:`Frame`.
    '''

    __slots__ = (
        '_loaded',
        '_loaded_all',
        '_series',
        '_store',
        '_config',
        '_last_accessed',
        '_max_persist',
        )

    _series: Series
    _store: tp.Optional[Store]
    _config: StoreConfigMap

    STATIC = False

    @staticmethod
    def _deferred_series(labels: tp.Iterable[str]) -> Series:
        '''
        Return an object ``Series`` of ``FrameDeferred`` objects, based on the passed in ``labels``.
        '''
        return Series.from_element(FrameDeferred, index=labels, dtype=object)

    @classmethod
    def from_frames(cls,
            frames: tp.Iterable[Frame],
            *,
            config: StoreConfigMapInitializer = None,
            name: NameType = None,
            ) -> 'Bus':
        '''Return a :obj:`Bus` from an iterable of :obj:`Frame`; labels will be drawn from :obj:`Frame.name`.
        '''
        # could take a StoreConfigMap
        series = Series.from_items(
                    ((f.name, f) for f in frames),
                    dtype=object,
                    name=name,
                    )
        return cls(series, config=config)

    @classmethod
    def _from_store(cls,
            store: Store,
            *,
            config: StoreConfigMapInitializer = None,
            max_persist: tp.Optional[int],
            ) -> 'Bus':
        return cls(cls._deferred_series(store.labels()),
                store=store,
                config=config,
                max_persist=max_persist,
                )

    #---------------------------------------------------------------------------
    def __init__(self,
            series: Series,
            *,
            store: tp.Optional[Store] = None,
            config: StoreConfigMapInitializer = None,
            max_persist: tp.Optional[int] = None,
            ):
        '''
        Args:
            config: StoreConfig for handling :obj:`Frame` construction and exporting from Store.
            max_persist: When loading :obj:`Frame` from a :obj:`Store`, optionally define the maximum number of :obj:`Frame` to remain in the :obj:`Bus`, regardless of the size of the :obj:`Bus`. If more than ``max_persist`` number of :obj:`Frame` are loaded, least-recently loaded :obj:`Frame` will be replaced by ``FrameDeferred``. A ``max_persist`` of 1, for example, permits reading one :obj:`Frame` at a time without ever holding in memory more than 1 :obj:`Frame`.
        '''

        if series.dtype != DTYPE_OBJECT:
            raise ErrorInitBus(
                    f'Series passed to initializer must have dtype object, not {series.dtype}')

        if max_persist is not None:
            self._last_accessed: tp.Dict[str, None] = {}

        # do a one time iteration of series
        def gen() -> tp.Iterator[bool]:
            for label, value in series.items():
                if not isinstance(label, str):
                    raise ErrorInitBus(f'supplied label {label} is not a string.')

                if isinstance(value, Frame):
                    if max_persist is not None:
                        self._last_accessed[label] = None
                    yield True
                elif value is FrameDeferred:
                    yield False
                else:
                    raise ErrorInitBus(f'supplied {value.__class__} is not a Frame or FrameDeferred.')

        self._loaded = np.fromiter(gen(), dtype=DTYPE_BOOL, count=len(series))
        self._loaded_all = self._loaded.all()
        self._series = series
        self._store = store

        # Not handling cases of max_persist being greater than the length of the Series (might floor to length)
        if max_persist is not None and max_persist < self._loaded.sum():
            raise ErrorInitBus('max_persis cannot be less than the number of already loaded Frames')
        self._max_persist = max_persist

        # providing None will result in default; providing a StoreConfig or StoreConfigMap will return an appropriate map
        self._config = StoreConfigMap.from_initializer(config)

    #---------------------------------------------------------------------------
    # delegation

    def __getattr__(self, name: str) -> tp.Any:
        try:
            return getattr(self._series, name)
        except AttributeError:
            # fix the attribute error to reference the Bus
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'") from None

    #---------------------------------------------------------------------------
    # cache management

    def _iloc_to_labels(self,
            key: GetItemKeyType
            ) -> np.ndarray:
        '''
        Given a get-item key, translate to an iterator of loc positions.
        '''
        if isinstance(key, int):
            return [self.index.values[key],] # needs to be a list for usage in loc assignment
        return self.index.values[key]


    def _update_series_cache_iloc(self, key: GetItemKeyType) -> None:
        '''
        Update the Series cache with the key specified, where key can be any iloc GetItemKeyType.

        Args:
            key: always an iloc key.
        '''
        max_persist_active = self._max_persist is not None

        load: bool
        if self._loaded_all:
            load = False
        else:
            load = not self._loaded[key].all() # works with elements

        if not load and not max_persist_active:
            return

        if not load and max_persist_active: # must update LRU position
            if isinstance(key, INT_TYPES):
                labels = (self._series.index.iloc[key],)
            else:
                labels = self._series.index.iloc[key].values
            for label in labels: # update LRU position
                self._last_accessed[label] = self._last_accessed.pop(label, None)
            return

        # load and max_persist_active True or False
        if self._store is None:
            # there has to be a Store defined if we are partially loaded
            raise RuntimeError('no store defined')

        if max_persist_active:
            loaded_count = self._loaded.sum()

        index = self._series.index
        array = self._series.values.copy() # not a deepcopy
        targets = self._series.iloc[key] # key is iloc key
        if not isinstance(targets, Series):
            targets = {index[key]: targets} # present element as items

        for label, frame in targets.items(): # this is a Series, not a Bus
            idx = index.loc_to_iloc(label)

            if max_persist_active: # update LRU position
                self._last_accessed[label] = self._last_accessed.pop(label, None)

            if frame is FrameDeferred:
                # as we are iterating from `targets`, we might be holding on to references of Frames that we already removed in `array`; in this case we do not need to `read`, but we still need to update the new array
                frame = self._store.read(label, config=self._config[label])

            if not self._loaded[idx]:
                array[idx] = frame
                self._loaded[idx] = True # update loaded status
                if max_persist_active:
                    loaded_count += 1

            if max_persist_active and loaded_count > self._max_persist:
                assert loaded_count == self._max_persist + 1 # type: ignore

                label_remove = next(iter(self._last_accessed))
                del self._last_accessed[label_remove]
                idx_remove = index.loc_to_iloc(label_remove)
                self._loaded[idx_remove] = False
                array[idx_remove] = FrameDeferred
                loaded_count -= 1
                assert loaded_count >= 0

        array.flags.writeable = False
        self._series = Series(array,
                index=self._series._index,
                dtype=object,
                own_index=True,
                )
        self._loaded_all = self._loaded.all()

    def _update_series_cache_all(self) -> None:
        '''Load all Tables contained in this Bus.
        '''
        if not self._loaded_all:
            self._update_series_cache_iloc(NULL_SLICE)

    #---------------------------------------------------------------------------
    # extraction

    def _extract_iloc(self, key: GetItemKeyType) -> 'Bus':
        self._update_series_cache_iloc(key=key)

        # iterable selection should be handled by NP
        values = self._series.values[key]

        if not isinstance(values, np.ndarray): # if we have a single element
            return values #type: ignore
        series = Series(
                values,
                index=self._series._index.iloc[key],
                name=self._series._name)
        return self.__class__(series=series,
                store=self._store,
                config=self._config,
                max_persist=self._max_persist,
                )

    def _extract_loc(self, key: GetItemKeyType) -> 'Bus':

        iloc_key = self._series._index.loc_to_iloc(key)

        # NOTE: if we update before slicing, we change the local and the object handed back
        self._update_series_cache_iloc(key=iloc_key)

        values = self._series.values[iloc_key]

        if not isinstance(values, np.ndarray): # if we have a single element
            # NOTE: only support str labels, not IndexHierarchy
            # if isinstance(key, HLoc) and key.has_key_multiple():
            #     values = np.array(values)
            #     values.flags.writeable = False
            return values #type: ignore

        series = Series(values,
                index=self._series._index.iloc[iloc_key],
                own_index=True,
                name=self._series._name)
        return self.__class__(series=series,
                store=self._store,
                config=self._config,
                max_persist=self._max_persist,
                )


    @doc_inject(selector='selector')
    def __getitem__(self, key: GetItemKeyType) -> 'Bus':
        '''Selector of values by label.

        Args:
            key: {key_loc}
        '''
        return self._extract_loc(key)

    #---------------------------------------------------------------------------
    # interfaces

    @property
    def loc(self) -> InterfaceGetItem['Bus']:
        return InterfaceGetItem(self._extract_loc)

    @property
    def iloc(self) -> InterfaceGetItem['Bus']:
        return InterfaceGetItem(self._extract_iloc)

    # ---------------------------------------------------------------------------
    def __reversed__(self) -> tp.Iterator[tp.Hashable]:
        return reversed(self._series._index) #type: ignore

    def __len__(self) -> int:
        return self._series.__len__()

    #---------------------------------------------------------------------------
    # dictionary-like interface

    def items(self) -> tp.Iterator[tp.Tuple[str, tp.Any]]:
        '''Iterator of pairs of index label and value.
        '''
        self._update_series_cache_all()
        yield from self._series.items()

    @property
    def values(self) -> np.ndarray:
        '''A 1D array of values.
        '''
        self._update_series_cache_all()
        return self._series.values

    #---------------------------------------------------------------------------
    @doc_inject()
    def display(self,
            config: tp.Optional[DisplayConfig] = None
            ) -> Display:
        '''{doc}

        Args:
            {config}
        '''
        # NOTE: the key change over serires is providing the Bus as the displayed class
        config = config or DisplayActive.get()
        display_cls = Display.from_values((),
                header=DisplayHeader(self.__class__, self._series._name),
                config=config)
        return self._series._display(config, display_cls)

    #---------------------------------------------------------------------------
    # extended disciptors

    @property
    def mloc(self) -> Series:
        '''Returns a Series of tuples of dtypes, one for each loaded Frame.
        '''
        if not self._loaded.any():
            return Series.from_element(None, index=self._series._index)

        def gen() -> tp.Iterator[tp.Tuple[tp.Hashable, tp.Optional[tp.Tuple[int, ...]]]]:
            for label, f in zip(self._series._index, self._series.values):
                if f is FrameDeferred:
                    yield label, None
                else:
                    yield label, tuple(f.mloc)

        return Series.from_items(gen())

    @property
    def dtypes(self) -> Frame:
        '''Returns a Frame of dtypes for all loaded Frames.
        '''
        if not self._loaded.any():
            return Frame(index=self._series.index)

        f = Frame.from_concat(
                frames=(f.dtypes for f in self._series.values if f is not FrameDeferred),
                fill_value=None,
                ).reindex(index=self._series.index, fill_value=None)
        return tp.cast(Frame, f)

    @property
    def shapes(self) -> Series:
        '''A :obj:`Series` describing the shape of each loaded :obj:`Frame`.

        Returns:
            :obj:`tp.Tuple[int]`
        '''
        values = (f.shape if f is not FrameDeferred else None for f in self._series.values)
        return Series(values, index=self._series._index, dtype=object, name='shape')


    @property
    def nbytes(self) -> int:
        '''Total bytes of data currently loaded in the Bus.
        '''
        return sum(f.nbytes if f is not FrameDeferred else 0 for f in self._series.values)

    @property
    def status(self) -> Frame:
        '''
        Return a
        '''
        def gen() -> tp.Iterator[Series]:

            yield Series(self._loaded,
                    index=self._series._index,
                    dtype=DTYPE_BOOL,
                    name='loaded')

            for attr, dtype, missing in (
                    ('size', DTYPE_FLOAT_DEFAULT, np.nan),
                    ('nbytes', DTYPE_FLOAT_DEFAULT, np.nan),
                    ('shape', DTYPE_OBJECT, None)
                    ):

                values = (getattr(f, attr) if f is not FrameDeferred
                        else missing for f in self._series.values)
                yield Series(values, index=self._series._index, dtype=dtype, name=attr)

        return tp.cast(Frame, Frame.from_concat(gen(), axis=1))

    #---------------------------------------------------------------------------
    @doc_inject()
    def equals(self,
            other: tp.Any,
            *,
            compare_name: bool = False,
            compare_dtype: bool = False,
            compare_class: bool = False,
            skipna: bool = True,
            ) -> bool:
        '''
        {doc}

        Args:
            {compare_name}
            {compare_dtype}
            {compare_class}
            {skipna}
        '''

        if id(other) == id(self):
            return True

        if compare_class and self.__class__ != other.__class__:
            return False
        elif not isinstance(other, Bus):
            return False

        # defer updating cache
        self._update_series_cache_all()

        if len(self._series) != len(other._series):
            return False

        if compare_name and self._series._name != other._series._name:
            return False

        # NOTE: dtype self._series is always object

        if not self._series.index.equals(
                other._series.index,
                compare_name=compare_name,
                compare_dtype=compare_dtype,
                compare_class=compare_class,
                skipna=skipna,
                ):
            return False

        # can zip because length of Series already match
        for (frame_self, frame_other) in zip(
                self._series.values, other._series.values):
            if not frame_self.equals(frame_other,
                    compare_name=compare_name,
                    compare_dtype=compare_dtype,
                    compare_class=compare_class,
                    skipna=skipna,
                    ):
                return False

        return True
