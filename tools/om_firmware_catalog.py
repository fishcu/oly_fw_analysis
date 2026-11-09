#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Query OM's public firmware catalog, or inspect a saved response offline.

Uses placeholder identifiers; never connects to a camera. Optional download
saves the offered stock file locally and does not install anything.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ENDPOINT = 'https://fw01.om-digitalsolutions.net/ww_inform/fcache.do'


def request_xml(version, model_id='1220'):
    root = ET.Element('firmware_demand')
    values = [('revision', '0001'), ('mac_address', '00-00-00-00-00-00'),
              ('time', datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')),
              ('language', 'ENU'), ('application', 'FWUT'), ('type', '0000'),
              ('version', '00005000'), ('os', 'WIN'), ('country_code', '0001')]
    for name, value in values:
        ET.SubElement(root, name).text = value
    hardware = ET.SubElement(root, 'hardwares')
    ET.SubElement(hardware, 'firmup_mode').text = '0'
    camera = ET.SubElement(hardware, 'hardware_info')
    for name, value in [('hard_code', 'OLYE' + model_id + '00000000'),
                        ('firmware_version', version), ('serial_no', '000000000')]:
        ET.SubElement(camera, name).text = value
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--model-id', default='1220', help='four-digit catalog ID, e.g. 1420 for E-P7')
    ap.add_argument('--model-name', default='PEN-F', help='expected catalog model name')
    ap.add_argument('--installed', default='00001000', help='eight-digit installed build; not a desired download version')
    ap.add_argument('--response', type=Path, help='inspect saved XML instead of querying the network')
    ap.add_argument('--download', action='store_true', help='download the offered firmware; no installation')
    ap.add_argument('--compare', type=Path, help='compare a downloaded file against this local file')
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    if not re.fullmatch(r'[0-9]{8}', args.installed):
        ap.error('--installed must contain eight decimal digits')
    if not re.fullmatch(r'[0-9]{4}', args.model_id):
        ap.error('--model-id must contain four decimal digits')
    if args.compare and not args.download:
        ap.error('--compare requires --download')
    if args.out.exists():
        ap.error('output directory must not already exist')
    request = request_xml(args.installed, args.model_id)
    if args.response:
        response = args.response.read_bytes()
    else:
        req = urllib.request.Request(ENDPOINT, data=request, headers={
            'User-Agent': 'Olympus', 'Content-Type': 'text/xml; Charset=UTF-8'})
        with urllib.request.urlopen(req, timeout=40) as result:
            response = result.read(2_000_001)
        if len(response) > 2_000_000:
            raise ValueError('unexpectedly large catalog response')
    root = ET.fromstring(response)
    if root.tag != 'firmware_result':
        raise ValueError('unexpected catalog response root')
    entries = []
    for info in root.findall('./firmwares/firmware_info'):
        row = {node.tag: node.text or '' for node in info}
        if row.get('model_id') != args.model_id or row.get('model_name') != args.model_name:
            raise ValueError(f"unexpected model: {row.get('model_id')!r} / {row.get('model_name')!r}")
        entries.append(row)
    if len(entries) != 1:
        raise ValueError('expected one catalog entry for the requested model')
    row = entries[0]
    url = urllib.parse.urlsplit(row['url'])
    summary = {k: v for k, v in row.items() if k != 'url'}
    summary['url_without_temporary_signature'] = urllib.parse.urlunsplit(url._replace(query='', fragment=''))
    summary['signature_query_keys'] = list(urllib.parse.parse_qs(url.query))
    summary['network_catalog_query'] = args.response is None
    summary['source_response'] = str(args.response) if args.response else None
    summary['reported_installed_version'] = root.findtext('hardwares/hardware_info/firmware_version') if args.response else args.installed
    summary['catalog_endpoint'] = ENDPOINT
    summary['camera_accessed'] = False
    args.out.mkdir(parents=True)
    if not args.response:
        (args.out / 'request.xml').write_bytes(request)
    (args.out / 'response.xml').write_bytes(response)
    if args.download:
        if not row['file_name']:
            raise ValueError('catalog offers no downloadable update')
        if not re.fullmatch(r'OLY_E_' + args.model_id[:3] + r'_[0-9]{4}_0000_0000\.BIN', row['file_name']):
            raise ValueError('unexpected firmware filename')
        if not re.fullmatch(r'[0-9]{4}', row['version']):
            raise ValueError('unexpected firmware version')
        expected_paths = {
            '/OMDS/FIRMWARES/0001/' + args.model_id + '/' + row['file_name'],
            '/dslr/' + args.model_id + '/v' + row['version'] + '/' + row['file_name'],
        }
        if url.scheme != 'https' or url.netloc != 'dl01.om-digitalsolutions.net' or url.path not in expected_paths:
            raise ValueError('unexpected firmware URL')
        expected_size = int(row['file_size'])
        if not 0 < expected_size <= 1024 * 1024 * 1024:
            raise ValueError('unexpected firmware size')
        destination = args.out / row['file_name']
        received, digest = 0, hashlib.sha256()
        with urllib.request.urlopen(row['url'], timeout=60) as source, destination.open('xb') as output:
            while chunk := source.read(1024 * 1024):
                received += len(chunk)
                if received > expected_size:
                    raise ValueError('download exceeds catalog size')
                output.write(chunk)
                digest.update(chunk)
        if received != expected_size:
            raise ValueError('download size does not match catalog')
        summary['download'] = {'bytes': received, 'sha256': digest.hexdigest()}
        if args.compare:
            summary['download']['byte_equal_to_comparison'] = destination.read_bytes() == args.compare.read_bytes()
            summary['download']['comparison_file'] = str(args.compare)
    (args.out / 'catalog-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
