# coding=utf-8

''' This module is designed to use ONLY in the Jupyter Notebook. It is
 inspired on Tyler Erickson's contribution on
https://github.com/gee-community/ee-jupyter-contrib/blob/master/examples/getting-started/display-interactive-map.ipynb'''

import ipyleaflet
from ipywidgets import HTML, Tab, Text, Accordion, Checkbox, HBox
from IPython.display import display
import ee
if not ee.data._initialized: ee.Initialize()
from collections import OrderedDict
from . import tools
from .maptool import get_default_vis, inverse_coordinates, get_data,\
                     get_image_tile, get_geojson_tile, get_bounds, get_zoom,\
                     create_html
import json


class Map(ipyleaflet.Map):
    def __init__(self, **kwargs):
        # Change defaults
        kwargs.setdefault('center', [0, 0])
        kwargs.setdefault('zoom', 2)
        super(Map, self).__init__(**kwargs)
        # self.added_geometries = {}
        # self.added_images = {}
        self.is_shown = False
        self.EELayers = {}

        # CREATE TABS
        self.tabs = Tab()
        tab_names = ['Inspector', 'Assets', 'Tasks']

        ## widgets
        self.inspectorWid = Accordion()  # Inspector Widget
        self.assetsWid = Accordion()  # Assets Widget
        self.tasksWid = HTML()  # Tasks Widget

        childrenName = ['Inspector', 'Assets', 'Tasks']
        childrenWid =  [self.inspectorWid, self.assetsWid, self.tasksWid]

        # Dictonary to hold tab's widgets
        # (tab's name:widget)
        self.childrenDict = OrderedDict(zip(childrenName, childrenWid))

        # Set tabs children
        self.tabs.children = self.childrenDict.values()
        # Set tabs names
        for i, name in enumerate(tab_names):
            self.tabs.set_title(i, name)

        # Handlers
        self.tabs.observe(self.handle_change_tab)
        self.handlers = {'Inspector': self.handle_inspector}

        # First handler: Inspector
        self.on_interaction(self.handlers['Inspector'])

    @property
    def added_images(self):
        return sum(
            [1 for val in self.EELayers.values() if val['type'] == 'Image'])

    @property
    def added_geometries(self):
        return sum(
            [1 for val in self.EELayers.values() if val['type'] == 'Geometry'])

    def create_assets_tab(self):
        # ASSETS TAB
        # Get assets root
        rootid = ee.data.getAssetRoots()[0]['id']
        assets_list = ee.data.getList({'id': rootid})
        widlist = []
        namelist = []
        for asset in assets_list:
            wid = HTML('')
            widlist.append(wid)
            name = asset['id'].split('/')[-1]
            ty = asset['type']
            namelist.append('{} ({})'.format(name, ty))

        self.assetsWid.children = widlist
        for i, name in enumerate(namelist):
            self.assetsWid.set_title(i, name)

    def show(self, inspector=True):
        """ Show the Map on the Notebook """
        if not self.is_shown:
            # Layers Control
            lc = ipyleaflet.LayersControl()
            self.add_control(lc)
            self.is_shown = True

            if inspector:
                # Create Assets Tab
                self.create_assets_tab()
                # Create Object Inspector
                self.addTab('Objects', self.handle_object_inspector, Accordion())
                # Display
                display(self, self.tabs)
            else:
                display(self)
        elif inspector:
            display(self, self.tabs)
        else:
            display(self)

    def addImage(self, image, visParams=None, name=None, show=True,
                 opacity=None):
        """ Add an ee.Image to the Map

        :param image: Image to add to Map
        :type image: ee.Image
        :param visParams: visualization parameters. Can have the
            following arguments: bands, min, max.
        :type visParams: dict
        :param name: name for the layer
        :type name: str
        :return: the added layer
        :rtype: TileLayer
        """
        thename = name if name else 'Image {}'.format(self.added_images)

        # Check if layer exists
        if thename in self.EELayers.keys():
            print("Image with name '{}' exists already, please choose another name".format(thename))
            return

        params = get_image_tile(image, visParams, show, opacity)

        layer = ipyleaflet.TileLayer(url=params['url'],
                                     attribution=params['attribution'],
                                     name=thename)
        self.add_layer(layer)
        self.EELayers[thename] = {'type':'Image',
                               'object':image,
                               'visParams':visParams,
                               'layer':layer}
        return layer

    def addGeometry(self, geometry, visParams=None, name=None, show=True,
                    opacity=None, inspect={'data':None, 'reducer':None, 'scale':None}):
        """ Add a Geometry to the Map

        :param geometry: the Geometry to add to Map
        :type geometry: ee.Geometry
        :param visParams:
        :type visParams: dict
        :param name: name for the layer
        :type name: str
        :param inspect: when adding a geometry or a feature you can pop up data
            from a desired layer. Params are:
            :data: the EEObject where to get the data from
            :reducer: the reducer to use
            :scale: the scale to reduce
        :type inspect: dict
        :return: the added layer
        :rtype: TileLayer
        """
        thename = name if name else 'Geometry {}'.format(self.added_geometries)

        # Check if layer exists
        if thename in self.EELayers.keys():
            print("Layer with name '{}' exists already, please choose another name".format(thename))
            return

        params = get_geojson_tile(geometry, inspect)
        layer = ipyleaflet.GeoJSON(data=params['geojson'],
                                   name=thename,
                                   popup=HTML(params['pop']))
        self.add_layer(layer)
        self.EELayers[thename] = {'type':'Geometry',
                               'object': geometry,
                               'visParams':None,
                               'layer': layer}
        return layer

    def addImageCollection(self, collection, visParams=None, nametags=['id'],
                           show=False, opacity=None):
        """ Add every Image of an ImageCollection to the Map

        :param collection: the ImageCollection
        :type collection: ee.ImageCollection
        :param visParams: visualization parameter for each image. See `addImage`
        :type visParams: dict
        :param nametags: tags that will be the name for each image. It must be
            a list in which each element is a string. Each string can be any
            Image property, or one of the following:
            - system_date: the name will be the date of each Image
            - id: the name will be the ID of each Image (Default)
        :type nametags: list
        :param show: If True, adds and shows the Image, otherwise only add it
        :type show: bool
        """
        size = collection.size().getInfo()
        collist = collection.toList(size)
        separation = ' '
        for inx in range(size):
            img = ee.Image(collist.get(inx))
            name = ''
            properties = img.propertyNames().getInfo()
            for nametag in nametags:
                if nametag == 'id':
                    newname = img.id().getInfo()
                elif nametag == 'system_date':
                    newname = ee.Date(img.date()).format('YYYY-MM-dd').getInfo()
                elif nametag in properties:
                    newname = "{}:{}{}".format(nametag, img.get(nametag).getInfo(), separation)
                else:
                    newname = img.id().getInfo()

                name += newname
            self.addImage(img, visParams, str(name), show, opacity)


    def addLayer(self, eeObject, visParams=None, name=None, show=True,
                 opacity=None, **kwargs):
        """ Adds a given EE object to the map as a layer.

        :param eeObject: Earth Engine object to add to map
        :type eeObject: ee.Image || ee.Geometry || ee.Feature

        For ee.Image and ee.ImageCollection see `addImage`
        for ee.Geometry and ee.Feature see `addGeometry`
        """
        # CASE: ee.Image
        if isinstance(eeObject, ee.Image):
            return self.addImage(eeObject, visParams=visParams, name=name,
                                 show=show, opacity=opacity)
        # CASE: ee.Geometry
        elif isinstance(eeObject, ee.Geometry) or isinstance(eeObject, ee.Feature):
            geom = eeObject if isinstance(eeObject, ee.Geometry) else eeObject.geometry()
            kw = {'visParams':visParams, 'name':name, 'show':show, 'opacity':opacity}
            if kwargs.get('inspect'): kw.setdefault('inspect', kwargs.get('inspect'))
            return self.addGeometry(geom, **kw)
        # CASE: ee.ImageCollection
        elif isinstance(eeObject, ee.ImageCollection):
            proxy = eeObject.sort('system:time_start')
            mosaic = ee.Image(proxy.mosaic())
            thename = name if name else 'Mosaic {}'.format(self.added_images)
            return self.addImage(mosaic, visParams=visParams, name=thename,
                                 show=show, opacity=opacity)
        else:
            print("`addLayer` doesn't support adding the specified object to"
                  "the map")

    def removeLayer(self, name):
        """ Remove a layer by its name """
        if name in self.EELayers.keys():
            layer = self.EELayers[name]['layer']
            self.remove_layer(layer)
            self.EELayers.pop(name)
        else:
            print('Layer {} is not present in the map'.format(name))
            return

    def centerObject(self, eeObject, zoom=None, method=1):
        """ Center an eeObject

        :param eeObject:
        :param zoom:
        :param method: experimetal methods to estimate zoom for fitting bounds
            Currently: 1 or 2
        :type: int
        """
        bounds = get_bounds(eeObject)
        if isinstance(eeObject, ee.Geometry):
            centroid = eeObject.centroid().getInfo()['coordinates']
        elif isinstance(eeObject, ee.Feature) or isinstance(eeObject, ee.Image):
            centroid = eeObject.geometry().centroid().getInfo()['coordinates']
        elif isinstance(eeObject, list):
            pol = ee.Geometry.Polygon(inverse_coordinates(list))
            centroid = pol.centroid().getInfo()['coordinates']

        self.center = inverse_coordinates(centroid)
        if zoom:
            self.zoom = zoom
        else:
            self.zoom = get_zoom(bounds, method)

    def getCenter(self):
        """ Returns the coordinates at the center of the map.

        No arguments.
        Returns: Geometry.Point

        :return:
        """
        center = self.center
        coords = inverse_coordinates(center)
        return ee.Geometry.Point(coords)

    def getBounds(self, asGeoJSON=True):
        """ Returns the bounds of the current map view, as a list in the
        format [west, south, east, north] in degrees.

        Arguments:
        asGeoJSON (Boolean, optional):
        If true, returns map bounds as GeoJSON.

        Returns: GeoJSONGeometry|List<Number>|String
        """
        bounds = inverse_coordinates(self.bounds)
        if asGeoJSON:
            return ee.Geometry.Rectangle(bounds)
        else:
            return bounds

    def addTab(self, name, handler, widget=None):
        """ Add a Tab to the Panel. The handler is for the Map

        :param name: name for the new tab
        :type name: str
        :param handler: handle function for the new tab. Arguments of the
            function are:

            :type: the type of the event (click, mouseover, etc..)
            :coordinates: coordinates where the event occured [lon, lat]
            :widget: the widget inside the Tab
            :map: the Map instance

        :param widget: widget inside the Tab. Defaults to HTML('')
        :type widget: ipywidgets.Widget
        """
        # Widget
        wid = widget if widget else HTML('')
        # Get tab's children as a list
        tab_children = list(self.tabs.children)
        # Get a list of tab's titles
        titles = [self.tabs.get_title(i) for i, child in enumerate(tab_children)]
        # Check if tab already exists
        if name not in titles:
            ntabs = len(tab_children)
            # Add widget as a new children
            self.childrenDict[name] = wid
            tab_children.append(wid)
            # Overwrite tab's children
            self.tabs.children = tab_children
            # Set name of the new tab
            self.tabs.set_title(ntabs, name)
            # Set the handler for the new tab
            def proxy_handler(f):
                def wrap(**kwargs):
                    # Add widget to handler arguments
                    kwargs['widget'] = self.childrenDict[name]
                    coords = kwargs['coordinates']
                    kwargs['coordinates'] = inverse_coordinates(coords)
                    kwargs['map'] = self
                    return f(**kwargs)
                return wrap
            self.handlers[name] = proxy_handler(handler)
        else:
            print('Tab {} already exists, please choose another name'.format(name))

    def handle_change_tab(self, change):
        """ Handle function to trigger when tab changes """
        # Remove all handlers
        if change['name'] == 'selected_index':
            old = change['old']
            new = change['new']
            old_name = self.tabs.get_title(old)
            new_name = self.tabs.get_title(new)
            # Remove all handlers
            for handl in self.handlers.values():
                self.on_interaction(handl, True)
            # Set new handler
            if new_name in self.handlers.keys():
                self.on_interaction(self.handlers[new_name])

    def handle_inspector(self, **change):
        """ Handle function for the Inspector Widget """
        # Get click coordinates
        coords = inverse_coordinates(change['coordinates'])

        event = change['type'] # event type
        if event == 'click':  # If the user clicked
            # Clear children // Loading
            self.inspectorWid.children = [HTML('wait a second please..')]
            self.inspectorWid.set_title(0, 'Loading...')

            # create a point where the user clicked
            point = ee.Geometry.Point(coords)

            # First Accordion row text (name)
            first = 'Point {} at {} zoom'.format(coords, self.zoom)
            namelist = [first]
            wids4acc = [HTML('')] # first row has no content

            for name, obj in self.EELayers.items(): # for every added layer
                # name = obj['name']
                # IMAGES
                if obj['type'] == 'Image':
                    # Get the image's values
                    image = obj['object']
                    values = tools.get_value(image, point, 10, 'client')
                    values = tools.sort_dict(values)
                    # Create the content
                    img_html = ''
                    for band, value in values.items():
                        img_html += '<b>{}</b>: {}</br>'.format(band,
                                                                value)
                    wid = HTML(img_html)
                    # append widget to list of widgets
                    wids4acc.append(wid)
                    namelist.append(name)

            # Set children and children's name of inspector widget
            self.inspectorWid.children = wids4acc
            for i, n in enumerate(namelist):
                self.inspectorWid.set_title(i, n)

    def handle_object_inspector(self, **change):
        """ Handle function for the Object Inspector Widget """

        event = change['type'] # event type
        thewidget = change['widget']
        if event == 'click':  # If the user clicked
            # Clear children // Loading
            thewidget.children = [HTML('wait a second please..')]
            thewidget.set_title(0, 'Loading...')

            widgets = []
            i = 0

            for name, obj in self.EELayers.items(): # for every added layer
                the_object = obj['object']
                properties = the_object.getInfo()
                wid = create_accordion(properties)
                widgets.append(wid)
                thewidget.set_title(i, name)
                i += 1

            thewidget.children = widgets


def create_accordion(dictionary):
    """ Create an Accordion output from a dict object """
    widlist = []
    ini = 0
    widget = Accordion()
    for key, val in dictionary.items():
        if isinstance(val, dict):
            newwidget = create_accordion(val)
            widlist.append(newwidget)
        elif isinstance(val, list):
            # tranform list to a dictionary
            dictval = {k: v for k, v in enumerate(val)}
            newwidget = create_accordion(dictval)
            widlist.append(newwidget)
        else:
            value = HTML(str(val))
            widlist.append(value)
        widget.set_title(ini, key)
        ini += 1
    widget.children = widlist
    return widget