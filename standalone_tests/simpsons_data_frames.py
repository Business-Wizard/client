#!/usr/bin/env python

"""Trains a classifier for frames from the Simpsons.

Useful for testing data tables.
"""

# we need this so strings are written to bigquery as strings rather than bytes
from __future__ import unicode_literals

import math
import os
import subprocess

import keras
from keras.models import Sequential
from keras.layers import Conv2D, MaxPooling2D, Dropout, Dense, Flatten
from keras.preprocessing.image import ImageDataGenerator
from keras import optimizers
import numpy as np
import pandas
import six
import wandb

run = wandb.init()
config = run.config
config.img_size = 50
config.batch_size = 32
config.epochs = 0
config.train_path = os.path.join('simpsons', 'train')
config.test_path = os.path.join('simpsons', 'test')

# download the data if it doesn't exist
if not os.path.exists("simpsons"):
    print("Downloading Simpsons dataset...")
    subprocess.check_output(
        "curl https://storage.googleapis.com/wandb-production.appspot.com/mlclass/simpsons.tar.gz | tar xvz", shell=True)

# this is the augmentation configuration we will use for training
# see: https://keras.io/preprocessing/image/#imagedatagenerator-class
train_datagen = ImageDataGenerator(
    rescale=1./255)

# only rescaling augmentation for testing:
test_datagen = ImageDataGenerator(rescale=1./255)

# this is a generator that will read pictures found in
# subfolers of 'data/train', and indefinitely generate
# batches of augmented image data
train_generator = train_datagen.flow_from_directory(
    config.train_path,
    target_size=(config.img_size, config.img_size),
    batch_size=config.batch_size)

# this is a similar generator, for validation data
test_generator = test_datagen.flow_from_directory(
    config.test_path,
    target_size=(config.img_size, config.img_size),
    batch_size=config.batch_size)

model = Sequential()
model.add(Conv2D(32, (3, 3), input_shape=(
    config.img_size, config.img_size, 3), activation="relu"))
model.add(MaxPooling2D())
model.add(Flatten())
model.add(Dropout(0.4))
model.add(Dense(50, activation="relu"))
model.add(Dropout(0.4))
model.add(Dense(13, activation="softmax"))
model.compile(optimizer=optimizers.Adam(),
              loss='categorical_crossentropy', metrics=['accuracy'])

def results_data_frame(test_datagen, model):
    gen = test_datagen.flow_from_directory(
        config.test_path,
        target_size=(config.img_size, config.img_size),
        batch_size=config.batch_size, shuffle=False)

    class_cols = []
    class_names = []
    for class_col, i in sorted(six.iteritems(gen.class_indices), key=lambda c_i: c_i[1]):
        class_cols.append(class_col)
        class_names.append(class_col.replace('_', ' '))

    cards = []
    true_class_is = []
    true_classes = []
    true_probs = []
    pred_classes = []
    pred_probs = []
    class_probs = [[] for _ in class_names]

    num_batches = int(math.ceil(len(gen.filenames) / float(gen.batch_size)))
    #num_batches = 1
    for batch_i in range(num_batches):
        examples, truth = next(gen)
        preds = model.predict(np.stack(examples))

        this_true_class_is = [np.argmax(probs) for probs in truth]
        true_class_is.extend(this_true_class_is)
        true_classes.extend(class_names[i] for i in this_true_class_is)
        true_probs.extend(ps[i] for ps, i in zip(preds, true_class_is))
        pred_classes.extend(class_names[np.argmax(probs)] for probs in preds)
        pred_probs.extend(np.max(probs) for probs in preds)
        for cp, p in zip(class_probs, preds.T):
            cp.extend(p)

        base_i = batch_i * gen.batch_size

        cards.extend(
            '''```Predicted:  
{pred_class} ({pred_prob:.2%})  
Actual:  
{true_class} ({true_prob:.2%})  
![](https://api.wandb.ai/adrianbg/simpsons/tgw7wnqj/simpsons/{idx}.jpg)
```'''.format(
                true_class=true_classes[i],
                true_prob=true_probs[i],
                pred_class=pred_classes[i],
                pred_prob=pred_probs[i],
                idx=i,
            )
            for i in range(base_i, base_i + len(examples))
        )

    all_cols = ['wandb_example_id', 'image', 'card', 'true_class', 'true_prob', 'pred_class', 'pred_prob'] + class_cols
    frame_dict = {
        'wandb_example_id': [six.text_type(s) for s in gen.filenames[:len(cards)]],
        'image': [wandb.Image(os.path.join(config.test_path, f)) for f in gen.filenames[:len(cards)]],
        'card': cards,
        'true_class': true_classes,
        'true_prob': true_probs,
        'pred_class': pred_classes,
        'pred_prob': pred_probs,
    }
    for c, col in zip(class_cols, class_probs):
        frame_dict[c] = col

    table = pandas.DataFrame(frame_dict, columns=all_cols)

    number_cols = ['true_prob', 'pred_prob'] + class_cols
    table[number_cols] = table[number_cols].apply(pandas.to_numeric)
    #from IPython import embed; embed()

    return table


class ResultsDataFrameCallback(keras.callbacks.Callback):
    def on_epoch_end(self, epoch, logs=None):
        run.summary["results"] = results_data_frame(test_datagen, model)

model.fit_generator(
    train_generator,
    steps_per_epoch=len(train_generator),
    epochs=config.epochs,
    workers=4,
    callbacks=[ResultsDataFrameCallback()],
    validation_data=test_generator,
    validation_steps=len(test_generator))

if config.epochs == 0:
    #run.summary["results"] = results_data_frame(test_datagen, model)
    run.summary.update({ "results3": results_data_frame(test_datagen, model) })
