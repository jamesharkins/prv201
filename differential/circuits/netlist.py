"""Minimal parser/renderer for the ngspice netlist subset used by the circuit library.

Supported element letters: R, C, L, V, I, B, D, Q, X. Directives other than
``.include`` are kept verbatim; the ``.control`` block and ``.end`` are dropped
(the simulation layer writes its own control script).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from differential.circuits.units import parse_value

_TWO_NODE = {"R", "C", "L", "V", "I", "B", "D"}


@dataclass(frozen=True)
class Element:
    name: str
    nodes: tuple[str, ...]
    value: str

    @property
    def letter(self) -> str:
        return self.name[0].upper()

    @property
    def numeric_value(self) -> float | None:
        """Numeric value for R/C/L elements, else None."""
        if self.letter in {"R", "C", "L"}:
            return parse_value(self.value.split()[0])
        return None

    def line(self) -> str:
        return " ".join([self.name, *self.nodes, self.value])

    def with_value(self, value: str) -> Element:
        return Element(self.name, self.nodes, value)

    def with_nodes(self, nodes: tuple[str, ...]) -> Element:
        return Element(self.name, nodes, self.value)


@dataclass
class Netlist:
    title: str
    includes: list[str] = field(default_factory=list)
    elements: list[Element] = field(default_factory=list)
    directives: list[str] = field(default_factory=list)

    def element(self, name: str) -> Element:
        key = name.upper()
        for el in self.elements:
            if el.name.upper() == key:
                return el
        raise KeyError(name)

    def has(self, name: str) -> bool:
        key = name.upper()
        return any(el.name.upper() == key for el in self.elements)

    def names(self) -> list[str]:
        return [el.name for el in self.elements]

    def nodes(self) -> set[str]:
        out: set[str] = set()
        for el in self.elements:
            out.update(el.nodes)
        return out

    def render(self, include_paths: list[Path], extra_lines: list[str] | None = None) -> str:
        lines = [self.title]
        lines += [f".include {p}" for p in include_paths]
        lines += self.directives
        lines += [el.line() for el in self.elements]
        if extra_lines:
            lines += extra_lines
        return "\n".join(lines) + "\n"


def _logical_lines(text: str) -> list[str]:
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("+") and out:
            out[-1] = out[-1] + " " + stripped[1:].strip()
        else:
            out.append(line)
    return out


def _strip_inline_comment(line: str) -> str:
    # ngspice treats ';' (and '$ ' after whitespace) as the start of an inline comment.
    for marker in (";", " $ "):
        idx = line.find(marker)
        if idx >= 0:
            line = line[:idx]
    return line.strip()


def parse_netlist(text: str) -> Netlist:
    lines = _logical_lines(text)
    if not lines:
        raise ValueError("empty netlist")
    net = Netlist(title=lines[0])
    in_control = False
    in_subckt = False
    subckt_buf: list[str] = []
    for line in lines[1:]:
        s = _strip_inline_comment(line)
        if not s or s.startswith("*"):
            continue
        low = s.lower()
        if in_control:
            if low.startswith(".endc"):
                in_control = False
            continue
        if low.startswith(".control"):
            in_control = True
            continue
        if in_subckt:
            subckt_buf.append(s)
            if low.startswith(".ends"):
                net.directives.append("\n".join(subckt_buf))
                subckt_buf = []
                in_subckt = False
            continue
        if low.startswith(".subckt"):
            in_subckt = True
            subckt_buf = [s]
            continue
        if low.startswith(".end"):
            break
        if low.startswith(".include"):
            net.includes.append(s.split(None, 1)[1].strip().strip('"'))
            continue
        if s.startswith("."):
            net.directives.append(s)
            continue
        net.elements.append(_parse_element(s))
    return net


def _parse_element(s: str) -> Element:
    tokens = s.split()
    name = tokens[0]
    letter = name[0].upper()
    if letter in _TWO_NODE:
        if len(tokens) < 4:
            raise ValueError(f"malformed element line: {s!r}")
        return Element(name, (tokens[1], tokens[2]), " ".join(tokens[3:]))
    if letter == "Q":
        return Element(name, (tokens[1], tokens[2], tokens[3]), " ".join(tokens[4:]))
    if letter == "X":
        return Element(name, tuple(tokens[1:-1]), tokens[-1])
    raise ValueError(f"unsupported element letter in {s!r}")


def load_netlist(path: Path) -> Netlist:
    return parse_netlist(path.read_text())
