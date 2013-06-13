# -*- coding: utf-8 -*-

import os.path
from collections import OrderedDict
from xml.dom.minidom import parse

from toolbox2.exception import Toolbox2Exception


class BaseParser(object):
    ROOT_NAME = 'AssetMap'
    ROOT_PROPERTIES = [
        'Id',
        'AnnotationText',
        'Creator',
        'VolumeCount',
        'IssueDate',
        'Issuer'
    ]
    ASSET_NAME = 'Asset'
    ASSET_ID_NAME = 'Id'
    ASSET_PROPERTIES = [
        'Id',
        'AnnotationText',
        'PackingList'
    ]
    ASSETLIST_NAME = 'AssetList'

    def __init__(self, path):
        self.path = path
        self.dom = None

    def parse(self):
        data = {}
        self.dom = parse(self.path)

        root = self.dom.documentElement
        if root.nodeType != root.ELEMENT_NODE or root.localName != self.ROOT_NAME:
            raise Toolbox2Exception('%s has an invalid root element: %s' % (self.ROOT_NAME, root.localName))

        data[self.ASSETLIST_NAME] = OrderedDict()

        for node in root.childNodes:
            if node.nodeType != node.ELEMENT_NODE:
                continue
            if node.localName in self.ROOT_PROPERTIES:
                data[node.localName] = self._get_node_data(node)
            elif node.localName == self.ASSETLIST_NAME:
                data[self.ASSETLIST_NAME] = self._get_assetlist(node)

        return data

    def _get_node_data(self, node):
        child = node.firstChild
        if not child:
            return None
        if child.nodeType != child.TEXT_NODE:
            raise Toolbox2Exception('Invalid text node')
        return node.firstChild.data

    def _get_assetlist(self, assetlist_node):
        assetlist = OrderedDict()
        for node in assetlist_node.childNodes:
            if node.nodeType != node.ELEMENT_NODE:
                continue
            if node.localName == self.ASSET_NAME:
                asset = self._get_asset(node)
                if asset:
                    if self.ASSET_ID_NAME not in asset:
                        raise Toolbox2Exception('Asset %s has not %s key' % (asset, self.ASSET_ID_NAME))
                    assetlist[asset[self.ASSET_ID_NAME]] = asset
        return assetlist

    def _get_asset(self, asset_node):
        asset = {}
        for node in asset_node.childNodes:
            if node.nodeType != node.ELEMENT_NODE:
                continue
            if node.localName in self.ASSET_PROPERTIES:
                data = self._get_node_data(node)
                # Not SMPTE compliant but PackingList is empty on some DCP
                if not data and node.localName in ('PackingList', ):
                    data = 'true'
                asset[node.localName] = data
        return asset


class AssetMapParser(BaseParser):
    CHUNK_NAME = 'Chunk'
    CHUNK_PROPERTIES = [
        'Path',
        'VolumeIndex',
        'Offset',
        'Length'
    ]
    CHUNKLIST_NAME = 'ChunkList'

    def _get_asset(self, asset_node):
        asset = BaseParser._get_asset(self, asset_node)
        asset[self.CHUNKLIST_NAME] = []
        for node in asset_node.childNodes:
            if node.nodeType != node.ELEMENT_NODE:
                continue
            if node.localName == self.CHUNKLIST_NAME:
                chunk_list = self._get_chunk_list(node)
                if chunk_list:
                    asset[self.CHUNKLIST_NAME] = chunk_list
        return asset

    def _get_chunk_list(self, chunklist_node):
        chunklist = []
        for node in chunklist_node.childNodes:
            if node.nodeType != node.ELEMENT_NODE:
                continue
            if node.localName == self.CHUNK_NAME:
                chunk = {}
                for chunk_element in node.childNodes:
                    if chunk_element.nodeType != chunk_element.ELEMENT_NODE:
                        continue
                    if chunk_element.localName in self.CHUNK_PROPERTIES:
                        chunk[chunk_element.localName] = self._get_node_data(chunk_element)
                chunklist.append(chunk)
        return chunklist


class PackingListParser(BaseParser):

    ROOT_NAME = 'PackingList'
    ROOT_PROPERTIES = [
        'Id',
        'AnnotationText',
        'IconId',
        'IssueDate',
        'Issuer', 'Creator',
        'GroupId',
        # 'Signer',
        # 'Signature'
    ]
    ASSET_PROPERTIES = [
        'Id',
        'AnnotationText',
        'Hash',
        'Size',
        'Type',
        'OriginalFilename'
    ]


class CompositionPlaylistParser(BaseParser):
    ROOT_NAME = 'CompositionPlaylist'
    ROOT_PROPERTIES = [
        'Id',
        'AnnotationText',
        'IconId',
        'IssueDate',
        'Issuer',
        'Creator',
        'ContentTitleText',
        'ContentKind',
        # 'Signer',
        # 'Signature'
    ]
    ASSET_NAME = 'Reel'
    ASSET_PROPERTIES = [
        'Id',
        'AnnotationText'
    ]
    ASSETLIST_NAME = 'ReelList'

    REEL_ASSETLIST_NAME = 'AssetList'
    REEL_ASSET_NAMES = [
        'MainSound',
        'MainSubtitle',
        'MainPicture',
        'MainStereoscopicPicture',
        'MainMarkers'
    ]
    REEL_ASSET_PROPERTIES = [
        'Id',
        'AnnotationText',
        'EditRate',
        'InstrinsicDuration',
        'EntryPoint',
        'Duration',
        'FrameRate',
        'ScreenAspectRatio',
        'Language'
    ]

    def _get_asset(self, asset_node):
        reel = BaseParser._get_asset(self, asset_node)
        for node in asset_node.childNodes:
            if node.nodeType != node.ELEMENT_NODE:
                continue
            if node.localName == self.REEL_ASSETLIST_NAME:
                reel[self.REEL_ASSETLIST_NAME] = self._get_reel_assetlist(node)
                break
        return reel

    def _get_reel_assetlist(self, assetlist_node):
        assetlist = {}
        for node in assetlist_node.childNodes:
            if node.nodeType != node.ELEMENT_NODE:
                continue
            if node.localName in self.REEL_ASSET_NAMES:
                asset = self._get_reel_asset(node)
                if asset:
                    assetlist[node.localName] = asset
        return assetlist

    def _get_reel_asset(self, asset_node):
        asset = {}
        for node in asset_node.childNodes:
            if node.nodeType != node.ELEMENT_NODE:
                continue
            if node.localName in self.REEL_ASSET_PROPERTIES:
                asset[node.localName] = self._get_node_data(node)
        return asset


class DCPTrailer(object):
    def __init__(self, log, path):
        self.log = log
        self.path = path
        self.assetmap_path = None
        for filename in ('ASSETMAP', 'ASSETMAP.xml'):
            assetmap_path = os.path.join(self.path, filename)
            if os.path.exists(assetmap_path):
                self.assetmap_path = assetmap_path
                break

        if not self.assetmap_path:
            raise Toolbox2Exception('No ASSETMAP found in package: %s' % self.path)

        self.assetmap = AssetMapParser(self.assetmap_path).parse()
        self.pkl_path = os.path.join(path, self._get_pkl_path())
        self.pkl = PackingListParser(self.pkl_path).parse()
        self.cpl_path, self.cpl = self._find_cpl()
        self.video_essences, self.audio_essences, self.subtitle_essences = self._find_essences()

    def _get_pkl_path(self):
        for asset in self.assetmap.get('AssetList').values():
            if asset.get('PackingList', 'false').lower() == 'true':
                return self._get_asset_path(asset)
        raise Toolbox2Exception('No PackingList found in ASSETMAP')

    def _get_asset_path(self, asset):
        if not 'ChunkList' in asset:
            raise Toolbox2Exception('No ChunkList specified for PackingList asset (id = %s)' % asset['Id'])
        if not asset['ChunkList']:
            raise Toolbox2Exception('Empty ChunkList for PackingList asset (id = %s)' % asset['Id'])
        if 'Path' not in asset['ChunkList'][0]:
            raise Toolbox2Exception('No path specified for PackingList asset (id = %s)' % asset['Id'])

        path = asset['ChunkList'][0]['Path']
        if path.startswith('file:///'):
            path = path[8:]
        elif path.startswith('file://'):
            path = path[7:]
        return path

    def _get_asset_path_by_id(self, asset_id):
        asset = self.assetmap['AssetList'][asset_id]
        return self._get_asset_path(asset)

    def _get_assets_by_type(self, asset_type):
        assets = []
        for asset_id, asset in self.pkl.get('AssetList').iteritems():
            try:
                if asset_type in asset['Type']:
                    assets.append(asset)
            except KeyError:
                pass
        return assets

    def _find_cpl(self):
        assets = self._get_assets_by_type('text/xml')
        for asset in assets:
            asset_path = self._get_asset_path(self.assetmap['AssetList'][asset['Id']])
            path = os.path.join(self.path, asset_path)
            try:
                cpl = CompositionPlaylistParser(path).parse()
                return path, cpl
            except Toolbox2Exception:
                pass
        raise Toolbox2Exception('No CompositionPlayList found in package')

    def _find_essences(self):
        if not self.cpl['ReelList']:
            raise Toolbox2Exception('No reel found in CompositionPlaylist %s' % self.cpl_path)

        first_reel = None
        for reel in self.cpl['ReelList'].values():
            first_reel = reel
            break

        video_essences = []
        audio_essences = []
        subtitle_essences = []

        for asset_type, asset in first_reel['AssetList'].iteritems():
            if asset_type in ('MainPicture', 'MainStereoscopicPicture'):
                asset_path = self._get_asset_path(self.assetmap['AssetList'][asset['Id']])
                video_essences.append({'path': os.path.join(self.path, asset_path)})
            elif asset_type == 'MainSound':
                asset_path = self._get_asset_path(self.assetmap['AssetList'][asset['Id']])
                audio_essences.append({'path': os.path.join(self.path, asset_path), 'language': asset.get('Language')})
            elif asset_type == 'MainSubtitle':
                asset_path = self._get_asset_path(self.assetmap['AssetList'][asset['Id']])
                subtitle_essences.append({'path': os.path.join(self.path, asset_path)})
        return video_essences, audio_essences, subtitle_essences
