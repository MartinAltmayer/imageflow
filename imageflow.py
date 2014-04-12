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
import math, functools, threading

from PyQt4 import QtCore, QtGui
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
              "Curve which describes how images become smaller on both sides of the center. "
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
                         "Between 0 and 1; Ratio of reflection height divided by image height."),
    'reflectionAlpha': (float, 0.4,
                        "How good should the reflection be visible?"
                        "Between 0 (invisible) and 1 (visible like the original image)."),
    'fadeOut': (bool, False,
                "Fade out images on both sides."),
    'fadeStart': (float, 0.4,
                  "Number in [0, 1]. If fadeOut is True, images will start fading out on both sides at the "
                  "position specified by fadeStart, i.e. 0 means that all images will fade out, 1 means that "
                  "only images at the outermost position will fade out."),
}

OPTIONS_REBUILD_CACHE = ['size', 'background', 'reflection', 'reflectionFactor']


DEBUG_TIMES = False
if DEBUG_TIMES:
    import time
    _times = []


STATE_INIT, STATE_READY, STATE_FAILED = 1,2,3


class Image:
    """A single image in the flow. This contains basically a pixmap and the cached version of it (resized to
    ImageFlow.option('size') and with reflection added). Instead of submitting the pixmap directly a path
    may be given. In this case the pixmap will not be loaded until it is visible in the image flow. Also,
    if *rotate* is true (and Wand available) the image will be rotated according to EXIF data.
    """
    def __init__(self, path=None, pixmap=None, text=None):
        if path is None and pixmap is None:
            raise ValueError("Either path or pixmap must be given")
        self.path = path
        assert pixmap is None
        self.state = STATE_INIT
        self.text = text
        self.image = None
        self._cache = None
    
    def load(self, rotate=False):
        """Load the image as QImage from filesystem."""
        self.image = QtGui.QImage(self.path)
        if rotate:
            try:
                import wand.image
                w = wand.image.Image(filename=self.path)
                if 'exif:Orientation' in w.metadata:
                    orientation = w.metadata['exif:Orientation']
                    if orientation != 1:
                        # Rotations stuff (read from EXIF data)
                        rotate = QtGui.QTransform()
                        if orientation == "6":
                            self.image = self.image.transformed(rotate.rotate(90))
                        elif orientation == "8":
                            self.image = self.image.transformed(rotate.rotate(270))
                        elif orientation == "3":
                            self.image = self.image.transformed(rotate.rotate(180))
            except ImportError as e:
                pass
            except Exception as e:
                print(e)
       
    def cache(self):
        if isinstance(self._cache, QtGui.QImage):
            self._cache = QtGui.QPixmap(self._cache)
        return self._cache
        
    def createCache(self, options):
        """Create the cached version of this image using the specified options (from ImageFlow.options).
        The cache version contains the resized image together with its reflection."""
        if self.image is None:
            self.load(options['rotate'])
        if self.image.isNull():
            self._cache = self.image
            self.state = STATE_FAILED
            return
        
        w = options['size'].width()
        h = options['size'].height()
        
        # For some reason drawing the result of pixmap.scaled gives better results than doing the same
        # scaling directly when drawing (drawPixmap(QtCore.QRect(0,0,w,h), pixmap))
        # Setting the SmoothPixmapTransform rendering hint does not change this behavior.
        image = self.image.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        w = image.width()
        h = image.height()
        if options['reflection']:
            hRefl = int(h * options['reflectionFactor'])
        else: hRefl = 0
        self._cache = QtGui.QImage(w, h + hRefl, QtGui.QImage.Format_RGB32)
        painter = QtGui.QPainter(self._cache)
        painter.drawImage(0, 0, image)
        
        if options['reflection'] and options['reflectionAlpha'] > 0:
            painter.setTransform(QtGui.QTransform(1, 0, 0, -1, 0, 0)) # draw reflection upside down
            source = QtCore.QRect(0, h-hRefl, w, hRefl)
            target = QtCore.QRect(0, -h-hRefl, w, hRefl)
            painter.drawImage(target, self._cache, source)
            painter.resetTransform()
            
            gradient = QtGui.QLinearGradient(0, 0, 0, 1)
            gradient.setCoordinateMode(QtGui.QGradient.ObjectBoundingMode)
            color = QtGui.QColor(options['background'])
            color.setAlpha((1.-options['reflectionAlpha'])*255)
            gradient.setColorAt(0, color)
            gradient.setColorAt(1, options['background'])
            painter.fillRect(0, h, w, hRefl, gradient)
        painter.end()
        self.state = STATE_READY
    
    def _clearCache(self):
        """Delete the cached version. Use this whenever options which affect
        the cached version have changed."""
        self.state = STATE_INIT
        self._cache = None


class ImageFlowWidget(QtGui.QWidget):
    indexChanged = QtCore.pyqtSignal(int)
    imagePressed = QtCore.pyqtSignal(Image)
    imageDblClicked = QtCore.pyqtSignal(Image)
    
    def __init__(self, data=None, loadAsync=True, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.WheelFocus)
        
        self.images = []
        self._pos = 0     
        self._o = {option: default for option, (optionType, default, _) in OPTIONS.items()}
        if data is not None:
            self.loadData(data)
        
        if loadAsync:
            self.worker = Worker(self._o) # use the same dict, so worker always uses current options
            self.worker.start()
        else: self.worker = None
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
        if any(k in OPTIONS_REBUILD_CACHE for k in changed):
            if self.worker is not None:
                self.worker.reset()
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
        if isinstance(point, QtCore.QPointF):
            point = point.toPoint()
        if len(self.images) == 0:
            return None
        o = self._o
        centerIndex = max(0, min(round(self._pos), len(self.images)-1))
        imagesLeft = imagesRight = o['imagesPerSide']
        if self._pos < round(self._pos):
            imagesLeft += 1
        elif self._pos > round(self._pos):
            imagesRight += 1
        # Check images in front first
        for index in _centerRange(max(0, centerIndex-imagesLeft), centerIndex,
                                  min(centerIndex+imagesRight+1, len(self.images))):
            rect = self.renderer.getRenderInfo(index, translate=True).rect
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
                self._startDrag(image)
            
    def _startDrag(self, image):
        if image.path is not None:
            drag = QtGui.QDrag(self)
            mimeData = QtCore.QMimeData()
            mimeData.setText(image.path)
            mimeData.setUrls([QtCore.QUrl(image.path)])
            if image.state == STATE_READY:
                mimeData.setImageData(image.image)
                drag.setPixmap(QtGui.QPixmap.fromImage(image.image).scaled(50, 50, Qt.KeepAspectRatio))
            drag.setMimeData(mimeData)
            drag.exec_()
            
    def resizeEvent(self, event):
        self.triggerRender()
        super().resizeEvent(event)
        
    def closeEvent(self, event):
        super().closeEvent(event)
        if event.isAccepted() and self.worker is not None:
            self.worker.shutdown()


class RenderInfo:
    def __init__(self, image, logicalX, rect, fullRect):
        self.image = image
        self.logicalX = logicalX
        self.rect = rect
        self.fullRect = fullRect
       

class Renderer:
    """Renderer for ImageFlow. The renderer will render the images of the given ImageFlowWidget into
    an internal buffer and draw that buffer onto the widget."""
    def __init__(self, widget):
        self.widget = widget
        self._o = widget._o
        self.init()
        if self.widget.worker is not None:
            self._frame = 0
            self._loadingAnim = QtGui.QPixmap('process-working.png')
            self.widget.worker.timer.timeout.connect(self._handleTimer)
    
    def init(self):
        """Initialize the internal buffer. Call this whenever the widget's size has changed."""
        self.size = self.widget.size()
        if self.size.isEmpty():
            return
        self.buffer = QtGui.QPixmap(self.size)
        self.dirty = True
       
    def _handleTimer(self):
        self._frame += 1
        if self._frame >= 32:
            self._frame = 1 # skip 0, see process-working.png
        self.widget.triggerRender()
        
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
    
    def renderImages(self):
        """Render all images."""
        o = self._o
        images = self.widget.images
        if len(images) == 0:
            return
        painter = QtGui.QPainter(self.buffer)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        # Using smooth transforms needs twice as much time (which is too little to notice). Because I can't
        # see any difference in image quality I don't use it.
        # Note that it makes no difference for the central image which is copied from cache without resizing.
        painter.translate(*self._getTranslation())
        centerIndex = max(0, min(round(self.widget._pos), len(images)-1))
        imagesLeft = imagesRight = o['imagesPerSide']
        if self.widget._pos < round(self.widget._pos):
            imagesLeft += 1
        elif self.widget._pos > round(self.widget._pos):
            imagesRight += 1
        imagesLeft = range(max(0, centerIndex-imagesLeft), centerIndex)
        imagesRight = range(centerIndex+1, min(centerIndex+imagesRight+1, len(self.widget.images)))
             
        if DEBUG_TIMES:
            if all(images[i]._cache is not None for i in
                range(max(0, centerIndex-imagesLeft),
                      min(len(images), centerIndex+imagesRight+1))):
                start = time.perf_counter()
            else: start = None
           
        # Load necessary images from center to the sides
        loadList = [images[index] for index in _centerRange(imagesLeft.start, centerIndex, imagesRight.stop)
                    if images[index].state == STATE_INIT]
        if self.widget.worker is not None:
            self.widget.worker.load(loadList)
        else:
            for image in loadList:
                image.createCache(o)
            
        # Render left images from left to center
        centerInfo = self.getRenderInfo(centerIndex)
        nextInfo = None
        for i in imagesLeft:
            info = nextInfo if nextInfo is not None else self.getRenderInfo(i)
            nextInfo = self.getRenderInfo(i+1) if i+1 in imagesLeft else centerInfo
            if info.image.state == STATE_READY and nextInfo.image.state == STATE_READY:
                self.renderImage(painter, info, nextRect=nextInfo.fullRect, left=True)
            else: self.renderImage(painter, info)
            
        # Render right images from right to center
        nextInfo = None
        for i in reversed(imagesRight):
            info = nextInfo if nextInfo is not None else self.getRenderInfo(i)
            nextInfo = self.getRenderInfo(i-1) if i-1 in imagesRight else centerInfo
            if info.image.state == STATE_READY and nextInfo.image.state == STATE_READY:
                self.renderImage(painter, info, nextRect=nextInfo.fullRect, left=False)
            else: self.renderImage(painter, info)
            
        # Render center image
        self.renderImage(painter, centerInfo)#, text=images[centerIndex].path[-30:])

        painter.end()
        if DEBUG_TIMES and start is not None:
            _times.append(time.perf_counter() - start)
            print(sum(_times) / len(_times))
       
    def renderImage(self, painter, info, text=None, nextRect=None, left=None):
        if not info.rect.isValid():
            return
        if info.image.state == STATE_INIT:
            self.renderLoadingImage(painter, info.rect)
        elif info.image.state == STATE_FAILED:
            self.renderMissingImage(painter, info.rect)
        else:
            pixmap = info.image.cache()
            rect = info.fullRect
            
            source = None
            if nextRect is not None and nextRect.isValid():
                # Skip the part of this image that will be hidden by nextRect
                if left:
                    if nextRect.top() <= rect.top() and nextRect.bottom() >= rect.bottom() \
                            and nextRect.right() >= rect.right():
                        part = (nextRect.left()-rect.left()) / rect.width()
                        source = QtCore.QRect(0, 0, part * pixmap.width(), pixmap.height())
                        rect.setRight(nextRect.left())
                else:
                    if nextRect.top() <= rect.top() and nextRect.bottom() >= rect.bottom() \
                            and nextRect.left() <= rect.left():
                        part = (rect.right()-nextRect.right()) / rect.width()
                        source = QtCore.QRect((1-part)*pixmap.width(), 0,
                                              part*pixmap.width(), pixmap.height())
                        rect.setLeft(nextRect.right())
            
            if source is None:
                painter.drawPixmap(rect, pixmap)
            else: painter.drawPixmap(rect, pixmap, source)
        
        if text is not None:
            textRect = QtCore.QRect(info.rect.left(), info.rect.bottom(), info.rect.width(), 30)
            pen = QtGui.QPen(Qt.white)
            painter.setPen(pen)
            painter.drawText(textRect, Qt.AlignCenter | Qt.AlignTop, text)
            
        if self._o['fadeOut']:
            if abs(info.logicalX) > self._o['fadeStart']:
                alpha = round(255 * max(0, 1-(abs(info.logicalX)-self._o['fadeStart'])))
                if alpha < 255:
                    color = QtGui.QColor(self._o['background'])
                    color.setAlpha(255-alpha)
                    painter.fillRect(info.fullRect, color)
        
    def getRenderInfo(self, index, translate=False):
        o = self._o
        image = self.widget.images[index]
        
        if index == self.widget.position(): # central image; the if is necessary if o['imagesPerSide']=0
            lx = 0
            z = 1
        else:
            # When seen from above, the images are arranged on a curve, with the central image
            # being "nearest" to the user and the outermost images being "farthest".
            # This is then used to determine the scale factors in the front view.
            # The curve is between [-1,1] for lx and [0,1] for z
            if o['curve'] == "arc":
                radians = (index-self.widget._pos) / o['imagesPerSide'] * o['segmentRads'] / 2
                lx = math.sin(radians)/abs(math.sin(o['segmentRads']/2))
                minCos = math.cos(o['segmentRads']/2)
                z = (math.cos(radians)-minCos)/(1.-minCos) # between 0 and 1
            elif o['curve'] == "v":
                lx = (index-self.widget._pos) / o['imagesPerSide']
                z = 1.-abs(lx)
            elif o['curve'] == "cos":
                lx = (index-self.widget._pos) / o['imagesPerSide']
                z = math.cos(lx*math.pi/2.) # between 0 and 1
            elif o['curve'] == "cossqrt":
                lx = (index-self.widget._pos) / o['imagesPerSide']
                if lx >= 0:
                    lx = math.sqrt(lx)
                else: lx = -math.sqrt(-lx)
                z = math.cos(lx*math.pi/2.) # between 0 and 1
            elif o['curve'] == "peak":
                lx = (index-self.widget._pos) / o['imagesPerSide']
                if lx >= 0:
                    z = (lx-1)**2
                else: z = (lx+1)**2
            elif o['curve'] == "gallery":
                lx = (index-self.widget._pos) / o['imagesPerSide']
                if abs(lx) >= 1./o['imagesPerSide']:
                    z = 0
                elif lx >= 0:
                    z = (lx*o['imagesPerSide'] - 1)**2
                else:
                    z = (lx*o['imagesPerSide'] + 1)**2
            else:
                assert False
         
        scale = o['minScale'] + min(1, z) * (1.-o['minScale'])
        if scale <= 0:
            rect = QtCore.QRect() # invalid rect
            return RenderInfo(image, lx, rect, rect)
             
        if image.state == STATE_READY:
            pixmap = image.cache()
            w = scale * pixmap.width()
            if o['reflection']:
                fullH = scale * pixmap.height()
                h = fullH / (1+o['reflectionFactor'])
            else:
                h = fullH = scale * pixmap.height()
        else:
            # placeholder/loading image will be drawn
            w = scale * o['size'].width()
            h = fullH = scale * o['size'].height()
         
        x = (lx * self._availableWidth()) / 2 # Scale x from [-1, 1] to pixel coordinates
        x -= w / 2 # lx refers to the center
        # The correct vertical offset y satisfies y + imageVAlign*scaledHeight = imageVAlign*maxHeight
        y = o['imageVAlign'] * (o['size'].height() - h)

        rect = QtCore.QRect(x, y, w, h)
        fullRect = QtCore.QRect(x, y, w, fullH) if fullH != h else rect
        
        if translate:
            rect.translate(*self._getTranslation())
            if fullRect is not rect:
                fullRect.translate(*self._getTranslation())
          
        return RenderInfo(image, lx, rect, fullRect)
          
    def renderMissingImage(self, painter, rect):
        """Render a crossed rectangle into *rect* to indicate an image that could not be loaded."""
        painter.fillRect(rect, QtGui.QColor(0, 0, 0, 160))
        pen = QtGui.QPen(Qt.darkGray)
        pen.setJoinStyle(Qt.MiterJoin)
        pen.setWidth(2)
        painter.setPen(pen)
        rect = QtCore.QRect(rect.x()+1, rect.y()+1, rect.width()-2, rect.height()-2)
        painter.drawRect(rect)
        painter.drawLine(rect.topLeft(), rect.bottomRight())
        painter.drawLine(rect.topRight(), rect.bottomLeft())
        
    def renderLoadingImage(self, painter, rect):
        """Render a crossed rectangle into *rect* to indicate an image that could not be loaded."""
        painter.fillRect(rect, QtGui.QColor(0, 0, 0, 160))
        pen = QtGui.QPen(Qt.darkGray)
        pen.setJoinStyle(Qt.MiterJoin)
        pen.setWidth(2)
        painter.setPen(pen)
        rect = QtCore.QRect(rect.x()+1, rect.y()+1, rect.width()-2, rect.height()-2)
        painter.drawRect(rect)
        x = 32 * (self._frame % 8)
        y = 32 * (self._frame // 8)
        source = QtCore.QRect(x, y, 32, 32)
        target = QtCore.QRect(source)
        target.moveCenter(rect.center())
        painter.drawPixmap(target, self._loadingAnim, source)
        
    def _availableWidth(self):
        """Return the width of the region that can be used for the center of images. This is a bit less than
        the widget's width to leave enough space at the edges so that the outer images are completely
        visible."""
        return self.buffer.width() - self._o['minScale'] * self._o['size'].width()

    def _getTranslation(self):
        """Return the translation of the coordinate system used for drawing images as (dx, dy)."""
        o = self._o
        dx = self.buffer.width() // 2
        if o['reflection']:
            necessaryHeight = (1+o['reflectionFactor']) * o['size'].height()
        else: necessaryHeight = o['size'].height()
        dy = max(0, int((self.buffer.height()-necessaryHeight) * o['vAlign']))
        return (dx, dy)


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


class Worker(threading.Thread):
    def __init__(self, options):
        super().__init__()
        self.daemon = True
        self.options = options
        self.timer = QtCore.QTimer()
        self.timer.setInterval(50)
        self._running = True
        self._newEvent = threading.Event() # wakes up the worker thread if something happens
        self._emptyEvent = None # is used to wait on the worker thread to finish
        self._loadList = []
    
    def load(self, images):
        self._loadList = images
        self._newEvent.set()
          
    def reset(self):
        self._emptyEvent = threading.Event()
        self.load([])
        self._emptyEvent.wait()
        self._emptyEvent = None
                
    def shutdown(self):
        self.timer.stop()
        self._running = False
        self._newEvent.set()
        
    def run(self):
        while self._running:
            loadList = self._loadList
            if len(loadList) == 0:
                self.timer.stop()
                if self._emptyEvent is not None:
                    self._emptyEvent.set()
                self._newEvent.wait()
                self._newEvent.clear()
            else:
                if not self.timer.isActive():
                    self.timer.start()
                for image in loadList:
                    if image.state == STATE_INIT:
                        image.createCache(self.options)
                    break # check for a new list
        
        
def _centerRange(start, center, stop):
    """This generator returns all numbers from *start* to *stop*-1. It returns these numbers ordered by their
    distance to *center*, starting with *center*.
    """
    yield center
    i = 1
    while center-i >= start or center+i < stop:
        if center-i >= start:
            yield center-i
        if center+i < stop:
            yield center+i
        i += 1
        

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
    configButton = QtGui.QPushButton("Options")
    configLayout.addWidget(configButton)
    configWindow = None
    def handleConfigButton():
        global configWindow
        if configWindow is None or not configWindow.isVisible():
            configWindow = ConfigWidget(imageWidget)
            configWindow.setWindowFlags(Qt.Tool)
            # Display below configButton
            configWindow.move(configButton.mapToGlobal(QtCore.QPoint(10, configButton.height()+10)))
            configWindow.show()
        else:
            configWindow.hide()
            configWindow = None
    configButton.clicked.connect(handleConfigButton)
    aboutButton = QtGui.QPushButton("Info")
    def handleAboutButton():
        QtGui.QMessageBox.information(widget, "About Image Flow", "Image Flow by Martin Altmayer. Licensed under GPL v3. See https://github.com/MartinAltmayer")
    aboutButton.clicked.connect(handleAboutButton)
    configLayout.addWidget(aboutButton)
    configLayout.addStretch()
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
