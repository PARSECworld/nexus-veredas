var GOOGLE_API_PROJECT = <Adicione Valor>

var nexusArea = ui.url.get('nexusArea', null)
var data = ui.url.get('data', null)

var outlineNames = ee.data.listAssets("projects/" + GOOGLE_API_PROJECT + "/assets/outlines_" + nexusArea + "_" + data)["assets"]
                    .map(function(asset) { return asset.name });
var outlines = outlineNames.map(function(outlineName) { return ee.Image(outlineName) });
var outlineGeometries = outlines.map(function(outline) { return outline.geometry() });
var outlineCollection = ee.ImageCollection.fromImages(outlines);

var satelliteImageNames = ee.data.listAssets("projects/" + GOOGLE_API_PROJECT + "/assets/satelliteImages_" + nexusArea + "_" + data)["assets"]
                    .map(function(asset) { return asset.name })
var satelliteImages = satelliteImageNames.map(function(satelliteImageName) {return ee.Image(satelliteImageName)})

Map.addLayer(outlineCollection);

var currentImageIndex = 1;
var currentImageLabel = ui.Label("1/" + outlines.length);
if (outlineGeometries[0] instanceof ee.Geometry) {
  Map.centerObject(outlineGeometries[0], 10); 
}

var prevButton = ui.Button('<', function() {
  updatePanel(currentImageIndex - 1, true); 
}, true);

var nextButton = ui.Button('>', function() {
  updatePanel(currentImageIndex + 1, true);
}, outlines.length <= 1)

function updatePanel(imageIndex, doCenter) {
  currentImageIndex = imageIndex;
  currentImageLabel.setValue(currentImageIndex + "/" + outlines.length);
  prevButton.setDisabled(currentImageIndex == 1);
  nextButton.setDisabled(currentImageIndex == outlines.length);
  thumbnail.setImage(satelliteImages[currentImageIndex - 1]);
  if (doCenter && outlineGeometries[currentImageIndex - 1] instanceof ee.Geometry) {
    Map.centerObject(outlineGeometries[currentImageIndex - 1], 10);
  }
}

var selectPanel = ui.Panel({
  widgets: [prevButton, currentImageLabel, nextButton],
  style: {width: '200px', margin: "0 50px 0 50px"},
  layout: ui.Panel.Layout.flow('horizontal')
})

var thumbnail = ui.Thumbnail(satelliteImages[0])
var panel = ui.Panel({
  widgets: [thumbnail, selectPanel],
  style: {position: 'bottom-left', width: '300px'}
});
Map.add(panel);

Map.onClick(function(coords) {
  var point = ee.Geometry.Point(coords.lon, coords.lat)
  outlineGeometries.forEach(function (outlineGeometry, i) {
    outlineGeometry.intersects(point).evaluate(function(isContained) {
      if (isContained) {
        var satelliteImageName = outlineNames[i].replace(/outline/g, "satelliteImage");
        var satelliteImageIndex = satelliteImageNames.indexOf(satelliteImageName)
        updatePanel(satelliteImageIndex + 1, false);
      }
    })
  })
})

Map.style().set('cursor', 'crosshair');