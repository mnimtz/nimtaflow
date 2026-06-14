"""XMP sidecar writer.

Creates/updates <filename>.xmp files alongside originals.  This is the
standard way tools like Lightroom, Darktable, and digiKam exchange metadata
without touching the original file.

Only activated when the 'write_xmp_sidecars' setting is enabled.
"""
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Optional

_NS = {
    "x":    "adobe:ns:meta/",
    "rdf":  "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "xmp":  "http://ns.adobe.com/xap/1.0/",
    "xmpMM": "http://ns.adobe.com/xap/1.0/mm/",
    "dc":   "http://purl.org/dc/elements/1.1/",
    "exif": "http://ns.adobe.com/exif/1.0/",
    "Iptc4xmpCore": "http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/",
}

for prefix, uri in _NS.items():
    ET.register_namespace(prefix, uri)


def _ns(prefix: str, tag: str) -> str:
    return f"{{{_NS[prefix]}}}{tag}"


def write_sidecar(
    photo_path: str,
    *,
    description: Optional[str] = None,
    user_description: Optional[str] = None,
    rating: Optional[int] = None,
    keywords: Optional[list] = None,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    caption: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    city: Optional[str] = None,
    country: Optional[str] = None,
) -> str:
    """Write an XMP sidecar and return its path."""
    photo = Path(photo_path)
    xmp_path = photo.with_suffix(".xmp")

    root = ET.Element(_ns("x", "xmpmeta"))
    root.set(_ns("x", "xmptk"), "PhotoFlow 1.0")
    rdf = ET.SubElement(root, _ns("rdf", "RDF"))
    desc = ET.SubElement(rdf, _ns("rdf", "Description"))
    desc.set(_ns("rdf", "about"), "")

    # XMP core
    desc.set(_ns("xmp", "MetadataDate"), datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))
    if rating is not None:
        desc.set(_ns("xmp", "Rating"), str(max(0, min(5, rating))))

    # Dublin Core
    combined_desc = description or ""
    if user_description:
        combined_desc = user_description  # user description takes precedence in XMP

    if combined_desc:
        dc_desc = ET.SubElement(desc, _ns("dc", "description"))
        alt = ET.SubElement(dc_desc, _ns("rdf", "Alt"))
        li = ET.SubElement(alt, _ns("rdf", "li"))
        li.set("{http://www.w3.org/XML/1998/namespace}lang", "x-default")
        li.text = combined_desc

    if title:
        dc_title = ET.SubElement(desc, _ns("dc", "title"))
        alt = ET.SubElement(dc_title, _ns("rdf", "Alt"))
        li = ET.SubElement(alt, _ns("rdf", "li"))
        li.set("{http://www.w3.org/XML/1998/namespace}lang", "x-default")
        li.text = title

    if caption:
        dc_cap = ET.SubElement(desc, _ns("dc", "description"))
        alt = ET.SubElement(dc_cap, _ns("rdf", "Alt"))
        li = ET.SubElement(alt, _ns("rdf", "li"))
        li.set("{http://www.w3.org/XML/1998/namespace}lang", "de")
        li.text = caption

    if artist:
        dc_creator = ET.SubElement(desc, _ns("dc", "creator"))
        seq = ET.SubElement(dc_creator, _ns("rdf", "Seq"))
        ET.SubElement(seq, _ns("rdf", "li")).text = artist

    if keywords:
        dc_subject = ET.SubElement(desc, _ns("dc", "subject"))
        bag = ET.SubElement(dc_subject, _ns("rdf", "Bag"))
        for kw in keywords:
            ET.SubElement(bag, _ns("rdf", "li")).text = kw

    # GPS via EXIF namespace
    if latitude is not None and longitude is not None:
        lat_ref = "N" if latitude >= 0 else "S"
        lon_ref = "E" if longitude >= 0 else "W"
        desc.set(_ns("exif", "GPSLatitude"), _decimal_to_dms(abs(latitude)))
        desc.set(_ns("exif", "GPSLatitudeRef"), lat_ref)
        desc.set(_ns("exif", "GPSLongitude"), _decimal_to_dms(abs(longitude)))
        desc.set(_ns("exif", "GPSLongitudeRef"), lon_ref)

    # IPTC location
    if city:
        desc.set(_ns("Iptc4xmpCore", "Location"), city)
    if country:
        desc.set(_ns("Iptc4xmpCore", "CountryName"), country)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(str(xmp_path), xml_declaration=True, encoding="UTF-8")
    return str(xmp_path)


def _decimal_to_dms(deg: float) -> str:
    d = int(deg)
    m_float = (deg - d) * 60
    m = int(m_float)
    s = (m_float - m) * 60
    return f"{d},{m},{s:.4f}"
