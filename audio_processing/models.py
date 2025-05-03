# audio_processing/models.py
from django.db import models
from lab_data.models import Experiments

class AudioExperimentData(models.Model):
    experiment = models.ForeignKey(Experiments, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    amplitude = models.FloatField()
    minima_detected = models.IntegerField(default=0)

    def __str__(self):
        return f"Аудиоданные для эксперимента #{self.experiment.id}"