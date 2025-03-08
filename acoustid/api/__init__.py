# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import json
import logging
import xml.etree.cElementTree as etree
from typing import Any, Dict, List, Union

import six
from six import BytesIO
from werkzeug.wrappers import Request, Response

from acoustid.handler import Handler
from acoustid.script import ScriptContext
from acoustid.utils import singular

logger = logging.getLogger(__name__)


def _serialize_xml_node(parent, data):
    # type: (etree.Element, Union[List[Any], Dict[str, Any], int, float, str]) -> None
    if isinstance(data, dict):
        _serialize_xml_dict(parent, data)
    elif isinstance(data, list):
        _serialize_xml_list(parent, data)
    else:
        parent.text = six.text_type(data)


def _serialize_xml_dict(parent, data):
    # type: (etree.Element, Dict[str, Any]) -> None
    for name, value in sorted(data.items()):
        if name.startswith("@"):
            parent.attrib[name[1:]] = six.text_type(value)
        else:
            elem = etree.SubElement(parent, name)
            _serialize_xml_node(elem, value)


def _serialize_xml_list(parent, data):
    # type: (etree.Element, List[Any]) -> None
    name = singular(parent.tag)
    for item in data:
        elem = etree.SubElement(parent, name)
        _serialize_xml_node(elem, item)


def serialize_xml(data, **kwargs):
    # type: (Union[List[Any], Dict[str, Any]], **Any) -> Response
    root = etree.Element("response")
    _serialize_xml_node(root, data)
    tree = etree.ElementTree(root)
    res = BytesIO()
    tree.write(res, encoding="UTF-8", xml_declaration=True)
    return Response(res.getvalue(), content_type="text/xml; charset=UTF-8", **kwargs)


def serialize_json(data, callback=None, **kwargs):
    # type: (Union[List[Any], Dict[str, Any], int, float, str], str | None, **Any) -> Response
    res = json.dumps(data, sort_keys=True)
    if callback:
        res = "%s(%s)" % (callback, res)
        mime = "application/javascript; charset=UTF-8"
    else:
        mime = "application/json; charset=UTF-8"
    return Response(res, content_type=mime, **kwargs)


def serialize_response(data, format, **kwargs):
    # type: (Union[List[Any], Dict[str, Any]], str, **Any) -> Response
    if format == "json":
        return serialize_json(data, **kwargs)
    elif format.startswith("jsonp:"):
        func = format.split(":", 1)[1]
        return serialize_json(data, callback=func, **kwargs)
    else:
        return serialize_xml(data, **kwargs)


def get_health_response(ctx, req, require_master=False):
    # type: (ScriptContext, Request, bool) -> Response
    from acoustid.wsgi_utils import is_shutting_down

    if require_master and ctx.config.cluster.role != "master":
        return Response("not the master server", content_type="text/plain", status=503)
    if is_shutting_down(ctx.config.website.shutdown_file_path):
        return Response("shutdown in process", content_type="text/plain", status=503)
    return Response("ok", content_type="text/plain", status=200)


class ReadOnlyHealthHandler(Handler):
    def handle(self, req):
        # type: (Request) -> Response
        return get_health_response(self.ctx, req)


class HealthHandler(ReadOnlyHealthHandler):
    def handle(self, req):
        # type: (Request) -> Response
        return get_health_response(self.ctx, req, require_master=True)
