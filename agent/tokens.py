"""Offline reproducible BPE measurement; distinct from provider billing usage."""
from functools import lru_cache
from pathlib import Path

TOKEN_MEASURE = 'tiktoken cl100k_base BPE; offline ranks; provider billing may differ'


@lru_cache(maxsize=1)
def encoding():
    import tiktoken
    from tiktoken.load import load_tiktoken_bpe
    from agent.capabilities import assets
    ranks = load_tiktoken_bpe(str(assets() / 'tokenizer' / 'cl100k_base.tiktoken'))
    return tiktoken.Encoding(name='codedesk_cl100k_base', pat_str=r"'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}++|\p{N}{1,3}+| ?[^\s\p{L}\p{N}]++[\r\n]*+|\s++$|\s*[\r\n]|\s+(?!\S)|\s", mergeable_ranks=ranks, special_tokens={})


def count_tokens(text):
    return len(encoding().encode(str(text), disallowed_special=()))


def limit_tokens(text, maximum=500):
    enc = encoding()
    return enc.decode(enc.encode(str(text), disallowed_special=())[:max(0, maximum)])
