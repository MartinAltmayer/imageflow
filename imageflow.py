# -*- coding: utf-8 -*-
# PyQt ImageFlow
# Copyright (C) 2013-2014 Martin Altmayer
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

class Image:
    """Relevant information about a single image file: path, full-size pixmap and a cache which contains the
    pixmap (resized ImageFlow.option('size')) and the reflection (if enabled).
    Pixmaps are only loaded when first requested.
    """
    def __init__(self, path):
        self.path = path
        self.pixmap = None
        self._cache = None
        
    def load(self):
        """Load the image's pixmap."""
        self.pixmap = QtGui.QPixmap(self.path)
       
    def cache(self, options):
        """Return the cached version of this image. *options* is the set of options
        returned by ImageFlow.options."""
        if self.pixmap is None:
            self.load()
        if self._cache is None:
            self._createCache(options)
        return self._cache
        
    def _createCache(self, options):
        """Create the cached version of this image using the specified options (from ImageFlow.options).
        The cache version contains the resized image together with its reflection."""
        w = options['size'].width()
        h = options['size'].height()
        if options['reflection']:
            hRefl = int(h * options['reflectionFactor'])
        else: hRefl = 0
        self._cache = QtGui.QPixmap(w, h + hRefl)
        painter = QtGui.QPainter(self._cache)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        rect = QtCore.QRect(0, 0, w, h)
        if self.pixmap is not None:
            painter.drawPixmap(rect, self.pixmap)
        else:
            painter.drawPixmap(rect, QtGui.QPixmap(':omg/image_missing.png'))
            # I'd like to use the SVG-version, but Qt is not able to draw it correctly
            #if not hasattr(self, '_imageMissingRenderer'):
            #    self._imageMissingRenderer = QtSvg.QSvgRenderer('image_missing.svg')
            #painter.fillRect(rect, Qt.black)
            #self._imageMissingRenderer.render(painter, QtCore.QRectF(rect))
        
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
    """
    Options:
    
    background: QColor to fill the background.
    size: QSize. The size of the central image.
    imagesPerSide: int. Number of images visible to the left and right of the central image.
    curve: string. The size of images is computed by arranging them (virtually and when seen from above)
           on a curve. The central image is "nearest" to the user and will use a scale factor of 1.
           The outermost images are "farthest" to the user and will be scaled using MIN_SCALE.
           One of:
                "arc" arc segment,
                "v": v-shape/abs function,
                "cos": cos function,
                "cossqrt": cos curve differently parametrized,
                "peak": peak build of two parabel halves,
                "gallery": show all images at MIN_SCALE except the central one.
    segmentRads: float in (0, pi]. Only for curve=="arc". Determines the length of the arc segment on which
                 images are positioned. Use π to arrange images on a semicircle.
    minScale: float in (0, 1]. Scale factor used for the outermost positions.
    vAlign: float in [0,1]. Vertical align of whole imageflow (or equivalently the central image).
            0: top, 1: bottom, linear in between (0.5: centered).
    imageVAlign: float in [0,1]. Vertical align of images among each other.
                 0: the top edge is aligned, 1: the bottom edge is aligned, linear in between.
    reflection: bool. Enable/disable reflection.
    reflectionFactor: float in [0,1]. Ratio of reflection height divided by image height
    fadeOut: bool. Fade out images on both sides.
    fadeStart: float in [0, 1]. If fadeOut is True, images will start fading out on both sides at the 
               position specified by fadeStart, i.e. 0 means that all images will fade out, 1 means that
               only images at the outermost position will fade out.
    """
    indexChanged = QtCore.pyqtSignal(int)
    imagePressed = QtCore.pyqtSignal(Image)
    imageDblClicked = QtCore.pyqtSignal(Image)
    
    def __init__(self, state=None, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.WheelFocus)
        
        self.images = []
        self._pos = 0     
        if state is None:
            state = {}   
        self._o = {
            'background': QtGui.QColor(*state['background']) \
                        if 'background' in state else QtGui.QColor(0,0,0),
            'size': QtCore.QSize(state['size'][0], state['size'][1]) \
                        if 'size' in state else QtCore.QSize(300, 300),
            'imagesPerSide': state.get('imagesPerSide', 5),
            'curve': state.get('curve', 'arc'),
            'segmentRads': 0.8*math.pi,
            'minScale': 0.3,
            'vAlign': 0.5 if not state.get('reflection') else 0.7,
            'imageVAlign': 0.8,
            'reflection': state.get('reflection', True),
            'reflectionFactor': 0.6,
            'fadeOut': state.get('fadeOut', True),
            'fadeStart': 0.4
        }
        
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
        types = {
            'background': QtGui.QColor,
            'size': QtCore.QSize,
            'imagesPerSide': int,
            'curve': str,
            'segmentRads': float,
            'minScale': float,
            'vAlign': float,
            'imageVAlign': float,
            'reflection': bool,
            'reflectionFactor': float,
            'fadeOut': bool,
            'fadeStart': float
        }
        changed = []
        for key, value in options.items(): # update only existing keys
            if key in self._o:
                type = types[key]
                if not isinstance(value, type) and not (type == float and isinstance(value, int)):
                    raise TypeError("Option '{}' must be of type {}. Received: {}".format(key, type, value))
                if value != self._o[key]:    
                    self._o[key] = value
                    changed.append(key)
        if any(k in changed for k in ['background', 'size', 'reflection', 'reflectionFactor']):
            for image in self.images:
                image._clearCache()
        if len(changed):
            self.triggerRender()
        
    def count(self):
        """Return the number of images."""
        return len(self.images)
        
    def setImages(self, paths):
        self.animator.stop()
        self.images = [Image(path) for path in paths]
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
        
    def setPosition(self, position):
        """Move directly to the image at *position*, i.e. without animation.
        *position* must be an index of self.images."""
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
        self.showPosition(self.animator.target() - round(event.delta()/120))
        event.accept()
    
    def imageAt(self, point):
        """Return the Image-instance at the given point (QPoint or QPointF) or None if no image is there."""
        if isinstance(point, QtCore.QPoint):
            point = QtCore.QPointF(point)
        o = self._o
        centerIndex = max(0, min(round(self._pos), len(self.images)-1))
        rect = self.renderer.imageRect(centerIndex)
        if rect.contains(point):
            return self.images[centerIndex]
        
        imagesLeft = imagesRight = o['imagesPerSide']
        if self._pos < round(self._pos):
            imagesLeft += 1
        elif self._pos > round(self._pos):
            imagesRight += 1
            
        if point.x() < rect.left():
            # test images to the left
            for index in reversed(range(max(0, centerIndex-imagesLeft), centerIndex)):
                rect = self.renderer.imageRect(index)
                if rect.contains(point):
                    return self.images[index]
                elif point.x() >= rect.left():
                    return None
        elif point.x() > rect.right():
            # test images to the right
            for index in range(centerIndex+1, min(centerIndex+imagesRight+1, len(self.images))):
                rect = self.renderer.imageRect(index)
                if rect.contains(point):
                    return self.images[index]
                elif point.x() <= rect.right():
                    return None
        return None
    
    def mousePressEvent(self, event):
        self._mousePressPosition = event.pos()
        image = self.imageAt(event.pos())
        if image is not None:
            self.imagePressed.emit(image)
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
                drag = QtGui.QDrag(self)
                #TODO
                mimeData = selection.MimeData(selection.Selection(levels.real, [wrapper]))
                drag.setMimeData(mimeData)
                drag.setPixmap(wrapper.element.getCover(100))
                drag.setHotSpot(QtCore.QPoint(50, 50))
                drag.exec_()
                self.setCursor(Qt.OpenHandCursor)
            
    def resizeEvent(self, event):
        self.triggerRender()
        super().resizeEvent(event)
        
    def createConfigWidget(self, parent):
        return ConfigWidget(self, parent)
    
    def state(self):
        bg = self.option('background')
        size = self.option('size')
        return {
            'background': (bg.red(), bg.green(), bg.blue()),
            'size': (size.width(), size.height()),
            'imagesPerSide': self.option('imagesPerSide'),
            'curve': self.option('curve'),
            'reflection': self.option('reflection'),
            'fadeOut': self.option('fadeOut'),
        }
        
      
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
        
    def renderImages(self):
        """Render all images."""
        if len(self.widget.images) == 0:
            return
        o = self._o
        painter = QtGui.QPainter(self.buffer)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        dx, dy = self._getTranslation()
        painter.translate(dx, dy)
        
        centerIndex = max(0, min(round(self.widget._pos), len(self.widget.images)-1))
        centerRect = self.renderImage(painter, centerIndex)
        clipRect = QtCore.QRect(-dx, -dy, dx+centerRect.left(), self.buffer.height())
        imagesLeft = imagesRight = o['imagesPerSide']
        if self.widget._pos < round(self.widget._pos):
            imagesLeft += 1
        elif self.widget._pos > round(self.widget._pos):
            imagesRight += 1
        for i in reversed(range(max(0, centerIndex-imagesLeft), centerIndex)):
            painter.setClipRect(clipRect)
            rect = self.renderImage(painter, i)
            if rect is None:
                break
            clipRect.setRight(min(clipRect.right(), rect.left()-1))
        clipRect = QtCore.QRect(centerRect.right(),
                                -dy,
                                self.buffer.width()-centerRect.right(),
                                self.buffer.height())
        for i in range(centerIndex+1, min(centerIndex+imagesRight+1, len(self.widget.images))):
            painter.setClipRect(clipRect)
            rect = self.renderImage(painter, i)
            if rect is None:
                break
            clipRect.setLeft(max(clipRect.left(), rect.right()))
            
        painter.end()

    def _getTranslation(self):
        """Return the translation of the coordinate system used for drawing images as (dx, dy)."""
        o = self._o
        dx = self.buffer.width() // 2
        if o['reflection']:
            necessaryHeight = (1+o['reflectionFactor']) * o['size'].height()
        else: necessaryHeight = o['size'].height()
        dy = int((self.buffer.height()-necessaryHeight) * o['vAlign'])
        return (dx, dy)
        
    def imageRect(self, index, translate=True):
        """Return the rectangle of a image (identified by an index within the list of images). The
        rectangle is the area in which the image is rendered, including parts that are behind other images.
        If *translate* is set to false the result will be relative to the coordinate system used for
        drawing. Otherwise it will be relative to the widgets usual coordinate system.
        """
        o = self._o
        w = o['size'].width()
        h = o['size'].height()
        
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
        y = (1-scale) * h * o['imageVAlign']
        
        pixmap = self.widget.images[index].cache(self._o)
        rect = QtCore.QRectF(round(x-scale*w/2), y, round(scale*pixmap.width()), scale*pixmap.height())
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
        o = self._o
        image = self.widget.images[index]
        pixmap = image.cache(self._o)
        rect = self.imageRect(index, translate=False)
        if pixmap.isNull():
            return QtCore.QRect(0,0,0,0)
        painter.drawPixmap(rect, pixmap, QtCore.QRectF(pixmap.rect()))

        if o['fadeOut']:
            # Scale x into [-1, 1] (this inverts a scaling in self.imageRect)
            x = rect.center().x() / self._availableWidth() * 2
            if abs(x) > o['fadeStart']:
                alpha = round(255 * max(0, 1-(abs(x)-o['fadeStart'])))
                if alpha < 255:
                    color = QtGui.QColor(o['background'])
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


# Test code to test imageflow without main application.
if __name__ == "__main__":
    import os, os.path, argparse
    parser = argparse.ArgumentParser(description="Show the images within one folder in an ImageFlow.")
    parser.add_argument('path', nargs='?', help="Path of the folder, defaults to current directory", default='.')
    parser.add_argument('--random', help="Shuffle the images.", action="store_true")
    args = parser.parse_args()
    
    app = QtGui.QApplication([])
    folder = os.path.abspath(os.path.expanduser(args.path))
    paths = [os.path.join(folder, filename) for filename in os.listdir(folder)]
    if args.random:
        import random
        random.shuffle(paths)
    widget = QtGui.QWidget()
    widget.resize(1400, 600)
    layout = QtGui.QVBoxLayout(widget)
    layout.setContentsMargins(0,0,0,0)
    layout.setSpacing(0)
    configLayout = QtGui.QHBoxLayout()
    curveBox = QtGui.QComboBox()
    curveBox.addItems([c[1] for c in CURVES])
    def handleCurveBox(index):
        widget.setOption('curve', curveBox.currentText())
    curveBox.currentIndexChanged.connect(handleCurveBox)
    configLayout.addWidget(curveBox)
    configLayout.addStretch()
    layout.addLayout(configLayout)
    imageWidget = ImageFlowWidget(None)
    imageWidget.setImages(paths)
    layout.addWidget(imageWidget)
    widget.show()
    imageWidget.setFocus(Qt.ActiveWindowFocusReason)
    app.exec_()
