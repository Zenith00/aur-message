import typing as ty
import functools

_DICT_FLATTEN_SEP = "⸱"  # u"\u2E31"
_LIST_FLATTEN_SEP = "→"  #

FlatContainer = ty.Union[dict, list]
FlatContainerType = ty.Union[ty.Type[dict], ty.Type[list]]
FlatKey = ty.Union[str, int]


def compose_keys(
        root: str,
        leaf: FlatKey,
        separation: FlatContainerType,
        dict_sep: str = _DICT_FLATTEN_SEP,
        list_sep: str = _LIST_FLATTEN_SEP
) -> str:
    sep = ""
    if root:
        if separation == list:
            sep = list_sep
        elif separation == dict:
            sep = dict_sep
        else:
            raise ValueError(f"Invalid separation {separation}")

    return root + sep + str(leaf)


def _flatten(
        d: FlatContainer,
        list_sep: str,
        dict_sep: str,
        key_str: str = ''
):
    if type(d) is dict:
        for k in d:
            yield from _flatten(d[k], list_sep, dict_sep, compose_keys(key_str, k, separation=dict))
    elif type(d) is list:
        for index, l_elem in enumerate(d):
            yield from _flatten(l_elem, list_sep, dict_sep, compose_keys(key_str, index, separation=list))
    else:
        yield key_str, d


def flatten(d: ty.Dict, list_sep=_LIST_FLATTEN_SEP, dict_sep=_DICT_FLATTEN_SEP) -> dict:
    return {k: v for k, v in _flatten(d, list_sep, dict_sep)}


class _Composition:
    def __init__(self):
        self.root = {}
        self.parent = self.root
        self.current_target = None

    def partial_compose(self, container: FlatContainer) -> ty.Callable:
        if isinstance(container, dict):
            return functools.partial(self.add_dict, container)
        elif isinstance(container, list):
            return functools.partial(self.add_list, container)
        else:
            raise ValueError(f"Incompatible container type supplied to "
                             f"partial_compose {type(container)} {container}")

    def set_parent_and_compose(
            self,
            new_target: FlatKey,
            layer_factory: ty.Callable
    ) -> None:
        self.partial_compose(self.parent)(self.current_target, layer_factory())
        self.parent = self.parent[self.current_target]
        self.current_target = new_target

    def reset(self) -> None:
        self.parent = self.root
        self.current_target = None

    @staticmethod
    def add_dict(d: dict, k: str, v: FlatContainer):
        if k not in d:
            d[k] = v

    @staticmethod
    def add_list(li: list, i: int, v: FlatContainer):
        li.extend(None for _ in range(i + 1 - len(li)))
        if li[i] is None:
            li[i] = v


def inflate(
        d: ty.Dict[str, str],
        dict_sep: str = _DICT_FLATTEN_SEP,
        list_sep: str = _LIST_FLATTEN_SEP
) -> dict:
    composer = _Composition()
    for k, v in d.items():
        dict_compositions = k.split(dict_sep)
        local_key: ty.Union[str, int] = dict_compositions[-1]

        for full_key in dict_compositions:
            dict_key: str
            indexes: ty.List[str]
            dict_key, *indexes = full_key.split(list_sep)

            composer.set_parent_and_compose(dict_key, dict)
            if indexes:
                for idx in map(int, indexes):
                    local_key = idx
                    composer.set_parent_and_compose(idx, list)

        composer.set_parent_and_compose(local_key, lambda: v)
        composer.reset()

    return composer.root[None]
