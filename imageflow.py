# -*- coding: utf-8 -*-
# PyQt ImageFlow
# Copyright (C) 2013-2014 Martin Altmayer <altmayer@posteo.de>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
import math, functools

from PyQt4 import QtCore, QtGui, QtSvg
from PyQt4.QtCore import Qt
translate = QtCore.QCoreApplication.translate

    
# Possible values for the 'curve' option along with user friendly titles
CURVES = [
    (translate("ImageFlow", "Arc"),     "arc"),
    (translate("ImageFlow", "V-Shape"), "v"),
    (translate("ImageFlow", "Cosine"),  "cos"),
    (translate("ImageFlow", "Peak"),    "peak"),
    (translate("ImageFlow", "Gallery"), "gallery"),
]

# Colors from which the user can choose in the configuration widget.
COLORS = [
    (translate("ImageFlow", "Black"),      QtGui.QColor(0,0,0)),
    (translate("ImageFlow", "Dark gray"),  QtGui.QColor(0x40, 0x40, 0x40)),
    (translate("ImageFlow", "Light gray"), QtGui.QColor(0x80, 0x80, 0x80)),
    (translate("ImageFlow", "White"),      QtGui.QColor(0xFF, 0xFF, 0xFF)),
]

# Available options. Options can be set via ImageFlowWidget.setOption. When this script is executed directly,
# options can also be given on the command line (try python imageflow.py --help).
# The tuples in this dict store the option type, default value and a description. Note that format
# descriptions in the latter only apply to the command line. ImageFlowWidget.setOption expects the type
# stored in the first tuple entry.
OPTIONS = {
    'size': (QtCore.QSize, QtCore.QSize(300, 300),
             "Maximal size of central image, e.g. 500x300. A single number can be used as shorthand for a "
             "square size."),
    'rotate': (bool, True,
               "Rotate images according to EXIF-data (requires Wand, http://docs.wand-py.org/)."),
    'imagesPerSide': (int, 5,
                      "Number of images visible to the left and right of the central image."),
    'background': (QtGui.QColor, Qt.black,
                   "Background color. Possible values are e.g. 'red', '#a2ee3f'. "
                   "See http://qt-project.org/doc/qt-4.8/qcolor.html#setNamedColor for all possibilities."),
    # The size of images is computed by arranging them (virtually and when seen from above)
    # on a curve. The central image is "nearest" to the user and will use a scale factor of 1.
    # The outermost images are "farthest" to the user and will be scaled using MIN_SCALE.
    'curve': (str, 'arc',
              "Curve which describes how images become smalle on both sides of the center. "
              "Possible values: "+','.join("'{}'".format(key) for _, key in CURVES)),
    'segmentRads': (float, 0.8*math.pi,
                    "Number in (0, pi]. Only for curve='arc'. Determines the length of the arc segment on "
                    "which images are positioned. Use π to arrange images on a semicircle."),
    'minScale': (float, 0.3, 
                 "Scale factor used for the outermost positions."),
    'vAlign': (float, 0.5,
               "Vertical align of whole image flow. 0=top, 0.5=center, 1=bottom, linear in between."),
    'imageVAlign': (float, 0.8,
                    "Vertical align of images within image flow. "
                    "0=top, 0.5=center, 1=bottom, linear in between."),
    'reflection': (bool, False,
                   "Add reflection."),
    'reflectionFactor': (float, 0.6, 
                         "Between 0 and 1; the higher the more visible is the reflection."),
    'fadeOut': (bool, True,
                "Fade out images on both sides."),
    'fadeStart': (float, 0.4,
                  "Number in [0, 1]. If fadeOut is True, images will start fading out on both sides at the "
                  "position specified by fadeStart, i.e. 0 means that all images will fade out, 1 means that "
                  "only images at the outermost position will fade out."),
}


DEBUG_TIMES = False
if DEBUG_TIMES:
    import time
    _times = []


class Image:
    """A single image in the flow. This contains basically a pixmap and the cached version of it (resized to
    ImageFlow.option('size') and with reflection added). Instead of submitting the pixmap directly a path
    may be given. In this case the pixmap will not be loaded until it is visible in the image flow. Also,
    if *rotate* is true (and Wand available) the image will be rotated according to EXIF data.
    """
    def __init__(self, path=None, pixmap=None):
        if path is None and pixmap is None:
            raise ValueError("Either path or pixmap must be given")
        self.path = path
        self.pixmap = pixmap
        self._cache = None
        
    def load(self, rotate=False):
        """Load the image's pixmap."""
        if self.pixmap is not None:
            return
        if rotate:
            try:
                import wand.image
                w = wand.image.Image(filename=self.path)
                if 'exif:Orientation' in w.metadata:
                    orientation = w.metadata['exif:Orientation']
                    if orientation != 1:
                        image = QtGui.QImage(self.path)
                        # Rotations stuff (read from EXIF data)
                        rotate = QtGui.QTransform()
                        if orientation == "6":
                            image = image.transformed(rotate.rotate(90))
                        elif orientation == "8":
                            image = image.transformed(rotate.rotate(270))
                        elif orientation == "3":
                            image = image.transformed(rotate.rotate(180))
                        self.pixmap = QtGui.QPixmap.fromImage(image)
                        return
            except ImportError:
                pass
            except Exception as e:
                print(e)
        self.pixmap = QtGui.QPixmap(self.path) # fallback
       
    def cache(self, options):
        """Return the cached version of this image. *options* is the set of options
        returned by ImageFlow.options."""
        if self.pixmap is None:
            self.load(options['rotate'])
        if self._cache is None:
            self._createCache(options)
        return self._cache
        
    def _createCache(self, options):
        """Create the cached version of this image using the specified options (from ImageFlow.options).
        The cache version contains the resized image together with its reflection."""
        w = options['size'].width()
        h = options['size'].height()
        
        pixmap = self.pixmap if self.pixmap is not None else QtGui.QPixmap(':omg/image_missing.png')
        #TODO            
        # I'd like to use the SVG-version, but Qt is not able to draw it correctly
        #if not hasattr(self, '_imageMissingRenderer'):
        #    self._imageMissingRenderer = QtSvg.QSvgRenderer('image_missing.svg')
        #painter.fillRect(rect, Qt.black)
        #self._imageMissingRenderer.render(painter, QtCore.QRectF(rect))
        
        # For some reason drawing the result of pixmap.scaled gives better results than doing the same
        # scaling directly when drawing (drawPixmap(QtCore.QRect(0,0,w,h), pixmap))
        # Setting the SmoothPixmapTransform rendering hint does not change this behavior.
        pixmap = pixmap.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        w = pixmap.width()
        h = pixmap.height()
        if options['reflection']:
            hRefl = int(h * options['reflectionFactor'])
        else: hRefl = 0
        self._cache = QtGui.QPixmap(w, h + hRefl)
        painter = QtGui.QPainter(self._cache)
        painter.drawPixmap(0, 0, pixmap)
        
        if options['reflection']:
            painter.setTransform(QtGui.QTransform(1, 0, 0, -1, 0, 0)) # draw reflection upside down
            source = QtCore.QRect(0, h-hRefl, w, hRefl)
            target = QtCore.QRect(0, -h-hRefl, w, hRefl)
            painter.drawPixmap(target, self._cache, source)
            painter.resetTransform()
            
            gradient = QtGui.QLinearGradient(0, 0, 0, 1)
            gradient.setCoordinateMode(QtGui.QGradient.ObjectBoundingMode)
            color = QtGui.QColor(options['background'])
            color.setAlpha(200)
            gradient.setColorAt(0, color)
            gradient.setColorAt(1, options['background'])
            painter.fillRect(0, h, w, hRefl, gradient)
            painter.end()
    
    def _clearCache(self):
        """Delete the cached version. Use this whenever options which affect
        the cached version have changed."""
        self._cache = None


class ImageFlowWidget(QtGui.QWidget):
    indexChanged = QtCore.pyqtSignal(int)
    imagePressed = QtCore.pyqtSignal(Image)
    imageDblClicked = QtCore.pyqtSignal(Image)
    
    def __init__(self, data=None, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.WheelFocus)
        
        self.images = []
        self._pos = 0     
        self._o = {option: default for option, (optionType, default, _) in OPTIONS.items()}
        if data is not None:
            self.loadData(data)
        
        self.renderer = Renderer(self)
        self.animator = Animator(self)
        self.clear() # initialize
     
    def option(self, key):
        """Return the value of the option with the given key."""
        return self._o[key]
      
    def options(self):
        """Return a dict with all options."""
        return self._o.copy()
    
    def setOption(self, key, value):
        """Set the option with the given key."""
        self.setOptions({key: value})
        
    def setOptions(self, options):
        """Set several options: *options* must be a dict mapping option keys to values. Options which are
        not contained in *options* remain unchanged."""

        changed = []
        for key, value in options.items():
            if key not in OPTIONS:
                raise KeyError("Invalid option '{}'.".format(key))
            optionType = OPTIONS[key][0]
            if not isinstance(value, optionType) and not (optionType == float and isinstance(value, int)):
                raise TypeError("Option '{}' must be of type {}. Received: {}"
                                .format(key, optionType, value))
            if value != self._o[key]:    
                self._o[key] = value
                changed.append(key)
        if any(k in changed for k in ['background', 'size', 'reflection', 'reflectionFactor']):
            for image in self.images:
                image._clearCache()
        if len(changed):
            self.triggerRender()
    
    def saveData(self):
        """Return a dict that stores the configuration of this widget using only standard data types. Use 
        this to save configuration persistently."""
        data = {}
        for option, value in self._o.items():
            if value == OPTIONS[option][1]: # default value
                continue
            if isinstance(option, QtGui.QColor):
                value = (value.red(), value.green(), value.blue())
            elif isinstance(option, QtCore.QSize):
                value = (value.width(), value.height())
            else: assert isinstance(value, (int, float, bool, str))
            data[option] = value
        return data
    
    def loadData(self, data):
        """Load configuration from a dict created by saveDate."""
        options = {}
        for option, value in data.items():
            if option not in OPTIONS:
                raise KeyError("Invalid option '{}'.".format(option))
            if OPTIONS[option][0] in (QtGui.QColor, QtCore.QSize):
                value = OPTIONS[option][0](*value)
            options[option] = value
        self.setOptions(options)
        
    def count(self):
        """Return the number of images."""
        return len(self.images)
       
    def setPaths(self, paths):
        """Display the images at the given paths."""
        self.setImages([Image(path=path) for path in paths])
       
    def setPixmaps(self, pixmaps):
        """Display the given QPixmaps."""
        self.setImages([Image(pixmap=pixmap) for pixmap in pixmaps])
        
    def setImages(self, images):
        """Display the given imageflow.Image-instances."""
        self.animator.stop()
        self.images = images
        self._pos = None
        if len(paths) > 0:
            self.setPosition(min(len(self.images)//2, self._o['imagesPerSide']))
        else: self.triggerRender()
         
    def clear(self):
        """Remove all images from display."""
        self.setImages([])
        
    def showPrevious(self):
        """Move to the previous image (using animation)."""
        pos = math.floor(self._pos)
        if pos == self._pos:
            pos -= 1
        self.showPosition(pos)
    
    def showNext(self):
        """Move to the next image (using animation)."""
        pos = math.ceil(self._pos)
        if pos == self._pos:
            pos += 1
        self.showPosition(pos)
    
    def showPosition(self, position):
        """Move to the image at *position* (using animation). *position* must be an index of self.images."""
        position = max(0, min(position, len(self.images)-1))
        if position != self._pos:
            self.animator.start(position)
        else: self.animator.stop()
       
    def position(self):
        """Return current position (an index in self.images)."""
        return self._pos
    
    def setPosition(self, position):
        """Move directly to the image at *position*, i.e. without animation."""
        position = max(0, min(position, len(self.images)-1))
        self.animator.stop()
        if position != self._pos:
            self._pos = position
            self.triggerRender()
            self.indexChanged.emit(position)
        
    def paintEvent(self, event):
        self.renderer.paint()
        
    def triggerRender(self):
        """Schedule a repaint."""
        self.renderer.dirty = True
        self.update()
        
    def createConfigWidget(self, parent):
        """Return a widget that allows to configure this ImageFlow."""
        return ConfigWidget(self, parent)
    
    def imageAt(self, point):
        """Return the Image-instance at the given point (QPoint or QPointF) or None."""
        index = self.indexAt(point)
        if index is not None:
            return self.images[index]
                               
    def indexAt(self, point):
        """Return the index (in self.images) of the image at the given point (QPoint or QPointF) or None
        if no image is there."""
        if isinstance(point, QtCore.QPoint):
            point = QtCore.QPointF(point)
        if len(self.images) == 0:
            return None
        o = self._o
        centerIndex = max(0, min(round(self._pos), len(self.images)-1))
        imagesLeft = imagesRight = o['imagesPerSide']
        if self._pos < round(self._pos):
            imagesLeft += 1
        elif self._pos > round(self._pos):
            imagesRight += 1
        for index in range(max(0, centerIndex-imagesLeft), min(centerIndex+imagesRight+1, len(self.images))):
            rect = self.renderer.imageRect(index, translate=True)
            if rect.contains(point):
                return index
        else:   
            return None
        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Left:
            self.showPosition(self.animator.target()-1)
            event.accept()
        elif event.key() == Qt.Key_Right:
            self.showPosition(self.animator.target()+1)
            event.accept()
        else:
            event.ignore()
            
    def wheelEvent(self, event):
        if self.animator.target() is not None:
            self.showPosition(self.animator.target() - round(event.delta()/120))
        event.accept()
    
    def mousePressEvent(self, event):
        self._mousePressPosition = event.pos()
        index = self.indexAt(event.pos())
        if index is not None:
            self.showPosition(index)
            self.imagePressed.emit(self.images[index])
        super().mousePressEvent(event)
            
    def mouseDoubleClickEvent(self, event):
        image = self.imageAt(event.pos())
        if image is not None:
            self.imageDblClicked.emit(image)
        event.accept()
    
    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and (event.pos() - self._mousePressPosition).manhattanLength() \
                                                >= QtGui.QApplication.startDragDistance():
            image = self.imageAt(event.pos())
            if image is not None:
                return
                #TODO
                drag = QtGui.QDrag(self)
                mimeData = selection.MimeData(selection.Selection(levels.real, [wrapper]))
                drag.setMimeData(mimeData)
                drag.setPixmap(wrapper.element.getCover(100))
                drag.setHotSpot(QtCore.QPoint(50, 50))
                drag.exec_()
                self.setCursor(Qt.OpenHandCursor)
            
    def resizeEvent(self, event):
        self.triggerRender()
        super().resizeEvent(event)
            
            
        
      
class Renderer:
    """Renderer for ImageFlow. The renderer will render the images of the given ImageFlowWidget into
    an internal buffer and draw that buffer onto the widget."""
    def __init__(self, widget):
        self.widget = widget
        self._o = widget._o
        self.init()
    
    def init(self):
        """Initialize the internal buffer. Call this whenever the widget's size has changed."""
        self.size = self.widget.size()
        if self.size.isEmpty():
            return
        self.buffer = QtGui.QPixmap(self.size)
        self.dirty = True
    
    def paint(self):
        """Render images if self.dirty is true. In any case copy the buffer to the ImageFlowWidget."""
        if self.widget.size() != self.size:
            self.init()
        
        if self.dirty:
            self.render()
        
        painter = QtGui.QPainter(self.widget)
        painter.drawPixmap(0, 0, self.buffer)
  
    def render(self):
        """Render background and all images."""
        self.buffer.fill(self._o['background'])
        self.renderImages()
        self.dirty = False
        
        
    def renderImage2(self, painter, index, rect, part, left):
        image = self.widget.images[index]
        pixmap = image.cache(self._o)
        if pixmap.isNull() or not rect.isValid():
            return
        if part == 1:
            painter.drawPixmap(rect.toRect(), pixmap)
        elif left:
            painter.drawPixmap(rect.toRect(), pixmap,
                               QtCore.QRect(0, 0, part*pixmap.width(), pixmap.height()))
        else:
            painter.drawPixmap(rect.toRect(), pixmap,
                               QtCore.QRect((1-part)*pixmap.width(), 0, part*pixmap.width(), pixmap.height()))
    
    def renderImages(self):
        """Render all images."""
        if len(self.widget.images) == 0:
            return
        o = self._o
        painter = QtGui.QPainter(self.buffer)
        # Using smooth transforms needs twice as much time (which is too little to notice). Because I can't
        # see any difference in image quality I don't use it.
        # Note that it makes no difference for the central image which is copied from cache without resizing.
        painter.translate(*self._getTranslation())
        centerIndex = max(0, min(round(self.widget._pos), len(self.widget.images)-1))
        imagesLeft = imagesRight = o['imagesPerSide']
        if self.widget._pos < round(self.widget._pos):
            imagesLeft += 1
        elif self.widget._pos > round(self.widget._pos):
            imagesRight += 1
             
        if DEBUG_TIMES:
            if all(self.widget.images[i]._cache is not None for i in
                range(max(0, centerIndex-imagesLeft),
                      min(len(self.widget.images), centerIndex+imagesRight+1))):
                start = time.perf_counter()
            else: start = None
            
        centerRect = self.imageRect(centerIndex)
        imagesLeft = range(max(0, centerIndex-imagesLeft), centerIndex)
        nextRect = None
        for i in imagesLeft:
            rect = nextRect if nextRect is not None else self.imageRect(i)
            nextRect = self.imageRect(i+1) if i+1 in imagesLeft else centerRect
            if nextRect.top() <= rect.top() and nextRect.bottom() >= rect.bottom() \
                    and nextRect.right() >= rect.right():
                part = (nextRect.left()-rect.left()) / rect.width()
                rect.setRight(nextRect.left())
            else: part = 1
            self.renderImage2(painter, i, rect, part, left=True)
            
        imagesRight = range(centerIndex+1, min(centerIndex+imagesRight+1, len(self.widget.images)))
        nextRect = None
        for i in reversed(imagesRight):
            rect = nextRect if nextRect is not None else self.imageRect(i)
            nextRect = self.imageRect(i-1) if i-1 in imagesRight else centerRect
            if nextRect.top() <= rect.top() and nextRect.bottom() >= rect.bottom() \
                    and nextRect.left() <= rect.left():
                part = (rect.right()-nextRect.right()) / rect.width()
                rect.setLeft(nextRect.right())
            else: part = 1
            self.renderImage2(painter, i, rect, part, left=False)
        self.renderImage2(painter, centerIndex, centerRect, 1, False)

        painter.end()
        if DEBUG_TIMES and start is not None:
            _times.append(time.perf_counter() - start)
            print(sum(_times) / len(_times))

    def _getTranslation(self):
        """Return the translation of the coordinate system used for drawing images as (dx, dy)."""
        o = self._o
        dx = self.buffer.width() // 2
        if o['reflection']:
            necessaryHeight = (1+o['reflectionFactor']) * o['size'].height()
        else: necessaryHeight = o['size'].height()
        dy = max(0, int((self.buffer.height()-necessaryHeight) * o['vAlign']))
        return (dx, dy)
       
    def imageRect(self, index, pixmap=None, translate=False):
        o = self._o
        w = o['size'].width()
        h = o['size'].height()
        if pixmap is None:
            pixmap = self.widget.images[index].cache(o)
        if pixmap.isNull():
            return QtCore.QRect()
        
        if index == self.widget.position():
            x = 0
            z = 1
        else:
            # When seen from above, the images are arranged on a curve, with the central image
            # being "nearest" to the user and the outermost images being "farthest".
            # This is then used to determine the scale factors in the front view.
            # The curve is between [-1,1] for x and [0,1] for z
            if o['curve'] == "arc":
                radians = (index-self.widget._pos) / o['imagesPerSide'] * o['segmentRads'] / 2
                x = math.sin(radians)/abs(math.sin(o['segmentRads']/2))
                minCos = math.cos(o['segmentRads']/2)
                z = (math.cos(radians)-minCos)/(1.-minCos) # between 0 and 1
            elif o['curve'] == "v":
                x = (index-self.widget._pos) / o['imagesPerSide']
                z = 1.-abs(x)
            elif o['curve'] == "cos":
                x = (index-self.widget._pos) / o['imagesPerSide']
                z = math.cos(x*math.pi/2.) # between 0 and 1
            elif o['curve'] == "cossqrt":
                x = (index-self.widget._pos) / o['imagesPerSide']
                if x >= 0:
                    x = math.sqrt(x)
                else: x = -math.sqrt(-x)
                z = math.cos(x*math.pi/2.) # between 0 and 1
            elif o['curve'] == "peak":
                x = (index-self.widget._pos) / o['imagesPerSide']
                if x >= 0:
                    z = (x-1)**2
                else: z = (x+1)**2
            elif o['curve'] == "gallery":
                x = (index-self.widget._pos) / o['imagesPerSide']
                if abs(x) >= 1./o['imagesPerSide']:
                    z = 0
                elif x >= 0:
                    z = (x*o['imagesPerSide'] - 1)**2
                else:
                    z = (x*o['imagesPerSide'] + 1)**2
            else:
                assert False
         
        # Scale x from [-1, 1] to pixel coordinates (x refers to the center of the image)
        x *= self._availableWidth() / 2
            
        if z > 1:
            z = 1
        scale = o['minScale'] + z * (1.-o['minScale'])
        if scale <= 0:
            return QtCore.QRect()
        
        # correct vertical align: y + imageVAlign*actualHeight = imageVAlign*maxHeight
        if o['reflection']:
            actualHeight = scale * pixmap.height() / (1+o['reflectionFactor'])
        else: actualHeight = scale * pixmap.height()
        y = o['imageVAlign'] * (o['size'].height() - actualHeight)
        
        rect = QtCore.QRectF(0, 0, scale*pixmap.width(), scale*pixmap.height())
        rect.translate(x-rect.width()/2, y)
        if translate:
            rect.translate(*self._getTranslation())
        return rect
    
    def _availableWidth(self):
        """Return the width of the region that can be used for the center of images. This is a bit less than
        the widget's width to leave enough space at the edges so that the outer images are completely
        visible."""
        return self.buffer.width() - self._o['minScale']*self._o['size'].width()
        
    def renderImage(self, painter, index):
        """Render the image at *index* (index within the list of images) using the given QPainter. Return
        the image's rectangle."""
        image = self.widget.images[index]
        pixmap = image.cache(self._o)
        if pixmap.isNull():
            return QtCore.QRect()
        rect = self.imageRect(index, pixmap=pixmap)
        if rect.isValid():
            painter.drawPixmap(rect.toRect(), pixmap)

            if False and self._o['fadeOut']:
                # Scale x into [-1, 1] (this inverts a scaling in self.imageRect)
                x = rect.center().x() / self._availableWidth() * 2
                if abs(x) > self._o['fadeStart']:
                    alpha = round(255 * max(0, 1-(abs(x)-self._o['fadeStart'])))
                    if alpha < 255:
                        color = QtGui.QColor(self._o['background'])
                        color.setAlpha(255-alpha)
                        painter.fillRect(rect, color)
            
        return rect


class Animator:
    """This class moves images during animation."""
    INTERVAL = 30
    
    def __init__(self, widget):
        self.widget = widget
        self.timer = QtCore.QTimer()
        self.timer.setInterval(self.INTERVAL)
        self.timer.timeout.connect(self.update)
        self._target = None
        self._start = None
        self._a = 4. / self.INTERVAL  # acceleration
        self._v = 0.                  # velocity
        
    def target(self):
        """Return the current target index."""
        if self._target is not None:
            return self._target
        else: return self.widget._pos
       
    def start(self, target):
        """Start animation moving to the given target index."""
        target = max(0, min(target, len(self.widget.images)-1))
        if not self.timer.isActive() \
                or (self._target - self.widget._pos) * (target - self.widget._pos) < 0: # different direction
            self._target = target
            self._v = 0.
            self.timer.start()
        else:
            self._target = target
       
    def stop(self):
        """Stop animation immediately."""
        self.timer.stop()
        self._target = None
        
    def update(self):
        """Called by the timer: Move animated images to the next position."""
        t = self._target
        if self.widget._pos == t:
            self.stop()
            self.widget.indexChanged.emit(t)
            return
        dist = abs(t - self.widget._pos)
        self._v = min(self._v + self._a, math.sqrt(2*self._a*dist))
        if t > self.widget._pos:
            self.widget._pos = min(t, self.widget._pos + self._v)
        else: self.widget._pos = max(t, self.widget._pos - self._v)
        self.widget.triggerRender()
        
        
class ConfigWidget(QtGui.QWidget):
    """Widget that allows to configure a ImageFlowWidget. Not all options can be accessed via the GUI."""
    def __init__(self, imageFlow, parent=None):
        super().__init__(parent)
        self.imageFlow = imageFlow
        layout = QtGui.QFormLayout(self)
        
        sliderLayout = QtGui.QHBoxLayout()
        sizeSlider = QtGui.QSlider(Qt.Horizontal) 
        sizeSlider.setMinimum(100)
        sizeSlider.setMaximum(500)
        size = imageFlow.option('size').width()
        sizeSlider.setValue(size)
        sizeSlider.valueChanged.connect(lambda x: imageFlow.setOption('size', QtCore.QSize(x,x)))
        sliderLayout.addWidget(sizeSlider)
        sizeLabel = QtGui.QLabel(str(size))
        sizeSlider.valueChanged.connect(lambda x,l=sizeLabel: l.setText(str(x)))
        sliderLayout.addWidget(sizeLabel)
        layout.addRow(translate("ImageFlow", "Image size"), sliderLayout) #TODO non-square sizes?

        self.curveBox = QtGui.QComboBox()
        for title, key in CURVES:
            self.curveBox.addItem(title, key)
            if key == imageFlow.option('curve'):
                self.curveBox.setCurrentIndex(self.curveBox.count()-1)
        self.curveBox.currentIndexChanged.connect(self._handleCurveBox)
        layout.addRow(translate("ImageFlow", "Curve"), self.curveBox)
        
        self.colorBox = QtGui.QComboBox()
        for title, key in COLORS:
            self.colorBox.addItem(title, key)
            if key == imageFlow.option('background'):
                self.colorBox.setCurrentIndex(self.colorBox.count()-1)
        self.colorBox.currentIndexChanged.connect(self._handleColorBox)
        layout.addRow(translate("ImageFlow", "Background"), self.colorBox)
        
        sliderLayout = QtGui.QHBoxLayout()
        numberSlider = QtGui.QSlider(Qt.Horizontal) 
        numberSlider.setMinimum(1)
        numberSlider.setMaximum(7)
        numberSlider.setValue(imageFlow.option('imagesPerSide'))
        numberSlider.valueChanged.connect(functools.partial(imageFlow.setOption, 'imagesPerSide'))
        sliderLayout.addWidget(numberSlider)
        sizeLabel = QtGui.QLabel(str(imageFlow.option('imagesPerSide')))
        numberSlider.valueChanged.connect(lambda x,l=sizeLabel: l.setText(str(x)))
        sliderLayout.addWidget(sizeLabel)
        layout.addRow(translate("ImageFlow", "Images per side"), sliderLayout)
        
        reflectionBox = QtGui.QCheckBox()
        reflectionBox.setChecked(imageFlow.option('reflection'))
        reflectionBox.toggled.connect(self._handleReflectionBox)
        layout.addRow(translate("ImageFlow", "Reflection"), reflectionBox)
        
        fadeOutBox = QtGui.QCheckBox()
        fadeOutBox.setChecked(imageFlow.option('fadeOut'))
        fadeOutBox.toggled.connect(functools.partial(imageFlow.setOption, 'fadeOut'))
        layout.addRow(translate("ImageFlow", "Fade out"), fadeOutBox)
        
    def _handleCurveBox(self, index):
        self.imageFlow.setOption('curve', self.curveBox.itemData(index))
        
    def _handleColorBox(self, index):
        self.imageFlow.setOption('background', self.colorBox.itemData(index))
        
    def _handleReflectionBox(self, checked):
        self.imageFlow.setOption('reflection', checked)
        self.imageFlow.setOption('vAlign', 0.7 if checked else 0.5)


# Stand-alone application to test the image flow.
if __name__ == "__main__":
    import os, os.path, argparse, sys
    
    # Parse arguments
    parser = argparse.ArgumentParser(description="Show the images within one folder in an ImageFlow.")
    parser.add_argument('path', nargs='?', help="Path of the folder, defaults to current directory", default='.')
    parser.add_argument('--random', help="Shuffle the images.", action='store_true')
    parser.add_argument('--no-random', dest='random', action='store_false')
    defaults={'random': False}
    for option, (optionType, default, description) in OPTIONS.items():
        if optionType is bool:
            parser.add_argument('--'+option, dest=option, action='store_true', help=description)
            parser.add_argument('--no-'+option, dest=option, action='store_false')
            defaults[option] = default
        else:
            if optionType in (QtGui.QColor, QtCore.QSize):
                optionType = str
            parser.add_argument('--'+option, type=optionType, help=description)
    parser.set_defaults(**defaults)
    args = parser.parse_args()
    
    # Load paths
    folder = os.path.abspath(os.path.expanduser(args.path))
    paths = [os.path.join(folder, filename) for filename in os.listdir(folder)]
    paths = [path for path in paths if os.path.splitext(path)[1].lower() in ['.png', '.jpg', '.jpeg', '.bmp']]
    if args.random:
        import random
        random.shuffle(paths)
       
    # Create GUI
    app = QtGui.QApplication([])
    widget = QtGui.QWidget()
    widget.setWindowTitle("Image flow")
    widget.resize(1400, 600)
    layout = QtGui.QVBoxLayout(widget)
    layout.setContentsMargins(0,0,0,0)
    layout.setSpacing(0)
    configLayout = QtGui.QHBoxLayout()
    curveBox = QtGui.QComboBox()
    curveBox.addItems([c[1] for c in CURVES])
    def handleCurveBox(index):
        imageWidget.setOption('curve', curveBox.currentText())
    curveBox.currentIndexChanged.connect(handleCurveBox)
    configLayout.addWidget(curveBox)
    configLayout.addStretch()
    aboutButton = QtGui.QPushButton("Info")
    def handleAboutButton():
        QtGui.QMessageBox.information(widget, "About Image Flow", "Image Flow by Martin Altmayer. Licensed under GPL v3. See https://github.com/MartinAltmayer")
    aboutButton.clicked.connect(handleAboutButton)
    configLayout.addWidget(aboutButton)
    layout.addLayout(configLayout)
    imageWidget = ImageFlowWidget()
    imageWidget.imagePressed.connect(lambda im: print("Pressed on {}".format(im.path)))
    imageWidget.imageDblClicked.connect(lambda im: print("Double clicked on {}".format(im.path)))
    layout.addWidget(imageWidget)
    
    # Set options
    options = {}
    for option, (optionType, default, description) in OPTIONS.items():
        value = getattr(args, option)
        if value is None:
            continue
        elif optionType is QtGui.QColor:
            value = QtGui.QColor(value)
            if not value.isValid():
                print("Invalid color specified for option '{}'.".format(option))
                sys.exit(1)
        elif optionType is QtCore.QSize:
            numbers = args.size.lower().split('x')
            if len(numbers) in [1,2] and all(len(n) > 0 for n in numbers) \
                        and all(c in '0123456789' for c in ''.join(numbers)):
                numbers = [max(1, min(int(n), 10000)) for n in numbers]
                if len(numbers) == 1:
                    numbers *= 2
                value = QtCore.QSize(*numbers)
            else:
                print("Invalid size specified for option '{}'.".format(option))
                sys.exit(1)
        elif option in ('vAlign', 'imageVAlign'):
            value = max(0, min(value, 1))
        elif option == 'imagesPerSide':
            value = max(0, min(value, 10))
            
        options[option] = value 
        
    imageWidget.setOptions(options)
       
    # Show
    imageWidget.setPaths(paths)
    widget.show()
    imageWidget.setFocus(Qt.ActiveWindowFocusReason)
    app.exec_()
