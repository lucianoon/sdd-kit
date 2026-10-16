"""IO de dados e artefatos: parsing inequívoco, caminhos confinados e escrita atômica."""
from __future__ import annotations

import json
import math
import os
import secrets
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path

import yaml

from .models import relative_path


class ArtifactError(ValueError):
    pass


class UniqueLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):  # sdd: no-mutate (deep equivale para mapas não recursivos do contrato)
        seen = set()
        # Verifica somente as chaves explícitas; overrides de YAML merge continuam válidos.
        for key, _ in node.value:
            if key.tag == "tag:yaml.org,2002:merge":
                continue
            value = self.construct_object(key, deep=deep)
            try:
                duplicate = value in seen
                seen.add(value)
            except TypeError as exc:
                raise yaml.constructor.ConstructorError(None, None, "chave YAML inválida", key.start_mark) from exc
            if duplicate:
                raise yaml.constructor.ConstructorError(None, None, f"chave YAML duplicada: {value}", key.start_mark)
        return super().construct_mapping(node, deep=deep)


def load_yaml(path: Path):
    return yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)


def parse_json(text: str):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError(f"chave JSON duplicada: {key}")
            out[key] = value
        return out

    def reject(value):
        raise ValueError(f"número JSON não finito: {value}")

    def number(value):
        result = float(value)
        return result if math.isfinite(result) else reject(value)

    return json.loads(text, object_pairs_hook=pairs, parse_constant=reject, parse_float=number)


def confined(root: Path, value: str) -> Path:
    try:
        relative_path(value)
    except ValueError as exc:
        raise ArtifactError(str(exc)) from exc
    anchor = root.resolve()
    path = anchor / value
    for current in [path, *path.parents]:
        if current == anchor:
            break
        if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
            raise ArtifactError(f"caminho com link não permitido: {value}")
    if not path.resolve().is_relative_to(anchor):
        raise ArtifactError(f"caminho fora do projeto: {value}")
    return path


@contextmanager
def _directory(root: Path, parent: Path):
    """No POSIX, prende a escrita ao diretório aberto, sem seguir links entre check e uso."""
    if os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW"):
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open(root.resolve(), flags)
        try:
            for part in parent.parts:
                try:
                    os.mkdir(part, dir_fd=fd)
                except FileExistsError:
                    pass
                child = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = child
            yield fd
        finally:
            os.close(fd)
    else:
        path = confined(root, parent.as_posix()) if parent.parts else root.resolve()
        path.mkdir(parents=True, exist_ok=True)
        if parent.parts:
            confined(root, parent.as_posix())
        yield None


def atomic_write(root: Path, value: str, content: str) -> Path:
    destination = confined(root, value)
    parent = Path(value).parent
    token = ".sdd-write-" + secrets.token_hex(12)
    try:
        with _directory(root, parent) as directory:
            if directory is not None:
                try:
                    # Defesa adicional: confined já recusa links e replace nunca escreve no alvo do link.
                    mode = os.stat(destination.name, dir_fd=directory, follow_symlinks=False).st_mode  # sdd: no-mutate (variante equivalente: destino é substituído)
                    if not stat.S_ISREG(mode):
                        raise ArtifactError(f"destino não é arquivo regular: {value}")
                except FileNotFoundError:
                    pass
                fd = os.open(token, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
                try:
                    with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
                        stream.write(content)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(token, destination.name, src_dir_fd=directory, dst_dir_fd=directory)
                finally:
                    try:
                        os.unlink(token, dir_fd=directory)
                    except FileNotFoundError:
                        pass
            else:
                fd, name = tempfile.mkstemp(prefix=token, dir=destination.parent)
                try:
                    with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
                        stream.write(content)
                        stream.flush()
                        os.fsync(stream.fileno())
                    confined(root, value)
                    os.replace(name, destination)
                finally:
                    Path(name).unlink(missing_ok=True)
    except OSError as exc:
        raise ArtifactError(f"não foi possível gravar {value}: {exc}") from exc
    return destination
