"""Life-science notation read by its segments: variants, karyotypes, genes.

The nomenclature standards fix where the pieces are (HGVS prefixes and
change types, ISCN abnormalities, HGNC symbol shape, JAX genotypes), and
practitioners' spoken forms fill in the words: "c dot", "A to G", "arg one
seventy-five his", "translocation between nine and twenty-two",
"knockout", "Eco R one" (Edvotek). Each function returns the words or
None when the text is not that notation; the normaliser calls them as
rules before its number and unit rules.
"""

from __future__ import annotations

import re

from natural_tts.reading.numbers import cardinal, digits

AMINO_ACIDS = {
    "Ala": "ala",
    "Arg": "arg",
    "Asn": "asn",
    "Asp": "asp",
    "Cys": "cys",
    "Gln": "gln",
    "Glu": "glu",
    "Gly": "gly",
    "His": "his",
    "Ile": "ile",
    "Leu": "leu",
    "Lys": "lys",
    "Met": "met",
    "Phe": "phe",
    "Pro": "pro",
    "Ser": "ser",
    "Thr": "thr",
    "Trp": "trp",
    "Tyr": "tyr",
    "Val": "val",
    "Sec": "sec",
    "Pyl": "pyl",
    "Xaa": "x a a",
    "Ter": "stop",
}
_CHANGES = {
    "del": "deletion",
    "dup": "duplication",
    "ins": "insertion",
    "inv": "inversion",
    "fs": "frameshift",
    "delins": "deletion insertion",
}
_DNA = re.compile(
    r"^(?P<prefix>[cgmnor])\.(?P<start>\d+)(?:_(?P<end>\d+))?"
    r"(?:(?P<ref>[ACGTU]+)>(?P<alt>[ACGTU]+)"
    r"|(?P<change>delins|del|dup|ins|inv)(?P<bases>[ACGTU]*))$"
)
_PROTEIN = re.compile(
    r"^p\.\(?(?P<ref>[A-Z][a-z]{2}|[A-Z])(?P<pos>\d+)"
    r"(?P<alt>[A-Z][a-z]{2}|[A-Z]|\*)?"
    r"(?:(?P<change>fs|del|dup|ins)(?:(?P<stop>Ter|\*)(?P<after>\d+)?)?)?\)?$"
)
_KARYOTYPE = re.compile(
    r"^(?P<count>\d{2}),(?P<sex>X[XY]|X|XXY|XYY)(?P<rest>(?:,.+)?)$"
)
_TRANSLOCATION = re.compile(r"^t\((\w+);(\w+)\)\((\w+);(\w+)\)$")
_ARM = re.compile(r"^(del|dup|inv)\((\w+)\)\((\w+)(?:;(\w+))?\)$")
_BAND = re.compile(
    r"^(?P<chrom>\d{1,2}|X|Y)(?P<arm>[pq])(?P<band>\d+)(?:\.(?P<sub>\d+))?$"
)
_GENOTYPE = re.compile(
    r"^(?P<gene>[A-Za-z][A-Za-z0-9]*)(?P<alleles>[+−-]/[+−-])$"
)
_ENZYME = re.compile(
    r"^(?P<genus>[A-Z][a-z]{2})(?P<strain>[A-Za-z]?)"
    r"(?P<roman>I{1,3}|IV|V|VI{0,3}|IX|X)$"
)
_ROMAN = {"I": 1, "V": 5, "X": 10}


def _position(number: str) -> str:
    """HGVS positions: short numbers as numbers, long ones digit by digit."""
    if len(number) <= 2:
        return cardinal(int(number))
    if len(number) == 3:
        return _three_digits(number)
    return digits(number)


def _three_digits(number: str) -> str:
    """Three-digit codes as said: "two ninety-three", "six hundred"."""
    if number.endswith("00"):
        return f"{cardinal(int(number[0]))} hundred"
    return f"{cardinal(int(number[0]))} {cardinal(int(number[1:]))}"


def three_digit_code(number: str) -> str:
    """Public form of the three-digit convention for identifiers (HEK293)."""
    return _three_digits(number)


def _residue(code: str) -> str:
    if code == "*":
        return "stop"
    return AMINO_ACIDS.get(code, code)


def hgvs_words(text: str) -> str | None:
    """Words for one HGVS variant description, or None."""
    dna = _DNA.match(text)
    if dna:
        words = f"{dna.group('prefix')} dot {_position(dna.group('start'))}"
        if dna.group("end"):
            words += f" to {_position(dna.group('end'))}"
        if dna.group("ref"):
            before, after = dna.group("ref"), dna.group("alt")
            return f"{words}, {' '.join(before)} to {' '.join(after)}"
        words += f" {_CHANGES[dna.group('change')]}"
        if dna.group("bases"):
            words += " " + " ".join(dna.group("bases"))
        return words
    protein = _PROTEIN.match(text)
    if protein and (protein.group("alt") or protein.group("change")):
        residue = _residue(protein.group("ref"))
        words = f"p dot {residue} {_position(protein.group('pos'))}"
        if protein.group("alt"):
            words += f" {_residue(protein.group('alt'))}"
        if protein.group("change"):
            words += f" {_CHANGES[protein.group('change')]}"
            if protein.group("stop"):
                words += " stop"
                if protein.group("after"):
                    words += f" {_position(protein.group('after'))}"
        return words
    return None


def karyotype_words(text: str) -> str | None:
    """Words for an ISCN karyotype such as ``46,XY,t(9;22)(q34;q11)``."""
    match = _KARYOTYPE.match(text)
    if not match:
        return None
    parts = [cardinal(int(match.group("count"))), " ".join(match.group("sex"))]
    for item in filter(None, match.group("rest").split(",")):
        if item[0] in "+-−" and item[1:].isalnum():
            kind = "trisomy" if item[0] == "+" else "monosomy"
            parts.append(f"{kind} {_chromosome(item[1:])}")
            continue
        translocation = _TRANSLOCATION.match(item)
        if translocation:
            a, b, pa, pb = translocation.groups()
            between = f"{_chromosome(a)} and {_chromosome(b)}"
            parts.append(f"translocation between {between}")
            parts.append(f"{_arm_words(pa)}, {_arm_words(pb)}")
            continue
        arm = _ARM.match(item)
        if arm:
            kind, chrom, first, second = arm.groups()
            words = (
                f"{_CHANGES[kind]} on {_chromosome(chrom)} {_arm_words(first)}"
            )
            if second:
                words += f" to {_arm_words(second)}"
            parts.append(words)
            continue
        return None
    return ", ".join(parts)


def _chromosome(label: str) -> str:
    return cardinal(int(label)) if label.isdigit() else " ".join(label)


def _arm_words(band: str) -> str:
    match = re.match(r"^([pq])(\d+)(?:\.(\d+))?$", band)
    if not match:
        return band
    words = f"{match.group(1)} {cardinal(int(match.group(2)))}"
    if match.group(3):
        words += f" point {cardinal(int(match.group(3)))}"
    return words


def band_words(text: str) -> str | None:
    """Words for a chromosome band such as ``17p13.1`` or ``Xq28``."""
    match = _BAND.match(text)
    if not match:
        return None
    words = f"{_chromosome(match.group('chrom'))} {match.group('arm')} "
    words += cardinal(int(match.group("band")))
    if match.group("sub"):
        words += f" point {cardinal(int(match.group('sub')))}"
    return words


def genotype_words(text: str) -> str | None:
    """Words for JAX genotype notation: ``Tp53-/-`` is "Tp53 knockout"."""
    match = _GENOTYPE.match(text)
    if not match:
        return None
    alleles = match.group("alleles").replace("−", "-")
    reading = {
        "-/-": "knockout",
        "+/-": "heterozygous",
        "-/+": "heterozygous",
        "+/+": "wild type",
    }
    return f"{match.group('gene')} {reading[alleles]}"


def enzyme_words(text: str) -> str | None:
    """Words for a restriction enzyme name: ``EcoRI`` is "Eco R one"."""
    match = _ENZYME.match(text)
    if not match:
        return None
    roman = match.group("roman")
    value = 0
    for index, char in enumerate(roman):
        unit = _ROMAN[char]
        if index + 1 < len(roman) and _ROMAN[roman[index + 1]] > unit:
            value -= unit
        else:
            value += unit
    words = match.group("genus")
    if match.group("strain"):
        words += f" {match.group('strain').upper()}"
    return f"{words} {cardinal(value)}"
