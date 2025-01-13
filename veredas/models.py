from django.db import models
import os

class ImageCollection(models.Model):
	nexusArea = models.CharField(max_length=255, blank=True, null=True)
	date = models.DateField(blank=True, null=True)

	class Meta: unique_together = ('nexusArea', 'date')

	def save(self, *args, **kwargs):
		existing_collection = ImageCollection.objects.filter(nexusArea=self.nexusArea, date=self.date).first()
		
		if existing_collection:
			return existing_collection
		super().save(*args, **kwargs)

class Image(models.Model):
	outline = models.FileField(upload_to='outlines', blank=True, null=True)
	satelliteImage = models.FileField(upload_to='satelliteImages', blank=True, null=True)
	imageCollection = models.ForeignKey(ImageCollection, on_delete=models.CASCADE, related_name='images', blank=True, null=True)

	def outlineName(self):
		return os.path.basename(self.outline.name)

	def satelliteImageName(self):
		return os.path.basename(self.satelliteImage.name)
