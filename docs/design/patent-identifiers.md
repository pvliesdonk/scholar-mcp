# Patent identifier normalization

Patent tools accept publication numbers with spaces, dots, commas, slash
notation, and lowercase letters. `_patent_numbers.normalize()` reduces these
spellings to one internal identifier:

```text
CC.number.KIND
```

The country and kind codes are uppercase, punctuation is removed from the
numeric portion, and a missing kind is represented by an empty final segment.
For example, `ep3491801b1`, `EP 3491801 B1`, and `EP.3491801.B1` all become
`EP.3491801.B1`.

The normalized identifier keys every patent section cache: bibliographic
data, claims, descriptions, families, legal events, and citations. PDF and
Markdown filenames use the same normalized components without dots. Keeping
normalization at the input boundary prevents different caller spellings from
creating duplicate rows or files.

Versions before the #444 fix could write lowercase kind codes into all six
database caches. Each affected table has a one-shot repair in `_REPAIRS` that
deletes only keys whose kind begins with a lowercase letter. The next request
then fills the uppercase key. Existing canonical rows remain intact.
