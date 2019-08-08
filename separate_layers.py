"""
ZERO VFX Shotgun Photoshop Plugin: Separating and Saving Layers
Developed by Rishi Pandey. Summer 2019.
"""

import os
import pprint
import tempfile
import uuid
import sys
import sgtk
#ADD THE PATH OF THE PSD_TOOLS2 LIBRARY
psd_tool2Path = "/Library/Frameworks/Python.framework/Versions/2.7/lib/python2.7/site-packages"
sys.path.append(psd_tool2Path)
from psd_tools2 import PSDImage


HookBaseClass = sgtk.get_hook_baseclass()


class PhotoshopUploadVersionPlugin(HookBaseClass):
    """
    Plugin for sending layers of photoshop documents to shotgun for review.
    """

    @property
    def icon(self):
        """
        Path to an png icon on disk
        """

        # look for icon one level up from this hook's folder in "icons" folder
        return os.path.join(
            self.disk_location,
            os.pardir,
            "icons",
            "review.png"
        )

    @property
    def name(self):
        """
        One line display name describing the plugin
        """
        return "Separate Layers"

    @property
    def description(self):
        """
        Verbose, multi-line description of what the plugin does. This can
        contain simple html for formatting.
        """
        publisher = self.parent

        shotgun_url = publisher.sgtk.shotgun_url

        media_page_url = "%s/page/media_center" % (shotgun_url,)
        review_url = "https://www.shotgunsoftware.com/features/#review"

        return """
        Separate layers and upload to Shotgun for review.<br><br>

        A <b>Version</b> entry will be created in Shotgun and a transcoded
        copy of the file will be attached to it. The file can then be reviewed
        via the project's <a href='%s'>Media</a> page, <a href='%s'>RV</a>, or
        the <a href='%s'>Shotgun Review</a> mobile app.
        """ % (media_page_url, review_url, review_url)

    @property
    def settings(self):
        """
        Dictionary defining the settings that this plugin expects to recieve
        through the settings parameter in the accept, validate, publish and
        finalize methods.

        A dictionary on the following form::

            {
                "Settings Name": {
                    "type": "settings_type",
                    "default": "default_value",
                    "description": "One line description of the setting"
            }

        The type string should be one of the data types that toolkit accepts as
        part of its environment configuration.
        """
        return {}

    @property
    def item_filters(self):
        """
        List of item types that this plugin is interested in.

        Only items matching entries in this list will be presented to the
        accept() method. Strings can contain glob patters such as *, for example
        ["maya.*", "file.maya"]
        """

        # we use "video" since that's the mimetype category.
        return ["photoshop.document"]

    def accept(self, settings, item):
        """
        Method called by the publisher to determine if an item is of any
        interest to this plugin. Only items matching the filters defined via the
        item_filters property will be presented to this method.

        A publish task will be generated for each item accepted here. Returns a
        dictionary with the following booleans:

            - accepted: Indicates if the plugin is interested in this value at
                all. Required.
            - enabled: If True, the plugin will be enabled in the UI, otherwise
                it will be disabled. Optional, True by default.
            - visible: If True, the plugin will be visible in the UI, otherwise
                it will be hidden. Optional, True by default.
            - checked: If True, the plugin will be checked in the UI, otherwise
                it will be unchecked. Optional, True by default.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process

        :returns: dictionary with boolean keys accepted, required and enabled
        """

        document = item.properties.get("document")
        if not document:
            self.logger.warn("Could not determine the document for item")
            return {"accepted": False}

        path = _document_path(document)

        if not path:
            # the document has not been saved before (no path determined).
            # provide a save button. the document will need to be saved before
            # validation will succeed.
            self.logger.warn(
                "The Photoshop document '%s' has not been saved." %
                (document.name,),
                extra=_get_save_as_action(document)
            )

        self.logger.info(
            "Photoshop '%s' plugin accepted document: %s" %
            (self.name, document.name)
        )
        return {
            "accepted": True,
            "checked": True
        }

    def validate(self, settings, item):
        """
        check to see if there are layers before publishing
        """
        """
        Validates the given item to check that it is ok to publish.

        Returns a boolean to indicate validity.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process

        :returns: True if item is valid, False otherwise.
        """

        document = item.properties["document"]
        path = _document_path(document)
        psdProject = PSDImage.open(path)
        for layer in psdProject:
            self.logger.info("Validated {layerName}.psd".format(layerName=layer.name))
        return True

    def publish(self, settings, item):
        """
        Executes the publish logic for the given item and settings.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        publisher = self.parent
        engine = publisher.engine
        document = item.properties["document"]

        path = _document_path(document)
        item.properties["upload_path"] = path
        item
        psdProject = PSDImage.open(path)

        #save layers to link and create new task to do so
        for layer in psdProject:
            layer.compose().save(layer.name+'.tiff')
            self.logger.info("Saved Layer {layerName}.psd".format(layerName=layer.name))
            publish = sgtk.util.register_publish(publisher.sgtk,
                                                item.context,
                                                os.path.join(os.path.dirname(path),layer.name+'.tiff'),
                                                layer.name,
                                                version_number=None,
                                                published_file_type="Rendered Image")



    def finalize(self, settings, item):
        """
        Execute the finalization pass. This pass executes once all the publish
        tasks have completed, and can for example be used to version up files.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        # version = item.properties["sg_version_data"]

        self.logger.info(
            "Version uploaded for Photoshop document",
            extra={
                "action_show_in_shotgun": {
                    "label": "Show Version",
                    "tooltip": "Reveal the version in Shotgun.",
                    "entity": None
                }
            }
        )

        upload_path = item.properties["upload_path"]

        # remove the tmp file
        if item.properties.get("remove_upload", False):
            try:
                os.remove(upload_path)
            except Exception:
                self.logger.warn(
                    "Unable to remove temp file: %s" % (upload_path,))
                pass

    def _get_version_entity(self, item):
        """
        Returns the best entity to link the version to.
        """

        if item.context.entity:
            return item.context.entity
        elif item.context.project:
            return item.context.project
        else:
            return None


def _get_save_as_action(document):
    """
    Simple helper for returning a log action dict for saving the document
    """

    engine = sgtk.platform.current_engine()

    # default save callback
    callback = lambda: engine.save_as(document)

    # if workfiles2 is configured, use that for file save
    if "tk-multi-workfiles2" in engine.apps:
        app = engine.apps["tk-multi-workfiles2"]
        if hasattr(app, "show_file_save_dlg"):
            callback = app.show_file_save_dlg

    return {
        "action_button": {
            "label": "Save As...",
            "tooltip": "Save the current document",
            "callback": callback
        }
    }


def _document_path(document):
    """
    Returns the path on disk to the supplied document. May be ``None`` if the
    document has not been saved.
    """

    try:
        path = document.fullName.fsName
    except Exception:
        path = None

    return path
