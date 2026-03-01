import os
import cv2
import numpy as np
import tensorflow as tf
from keras.preprocessing.image import ImageDataGenerator
from keras.callbacks import ModelCheckpoint, EarlyStopping

# 显存优化配置
gpus = tf.config.experimental.list_physical_devices('GPU')
if gpus:
    try:
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(gpu, True)  # 按需增长
        logical_gpus = tf.config.experimental.list_logical_devices('GPU')
        print(f"{len(gpus)} Physical GPUs, {len(logical_gpus)} Logical GPUs")
    except RuntimeError as e:
        print(e)

# 设置路径和参数
work_dir = 'D:/Vgg16/data'
train_data_path = os.path.join(work_dir, 'train')
test_data_path = os.path.join(work_dir, 'test')
weights_file_path = os.path.join(work_dir, 'Alex_Net.weights.h5')
image_size = (128, 128)
batch_size = 32
categories = ['bellflower', 'coreopsis', 'iris', 'orchid', 'rose', 'sunflower', 'tulip']

# 新增模型定义
def create_alexnet(input_shape, category_num):
    model = tf.keras.Sequential([
        tf.keras.layers.InputLayer(input_shape=input_shape),
        tf.keras.layers.Conv2D(64, 11, strides=4, activation='relu'),  # 原96→64
        tf.keras.layers.MaxPool2D(3, strides=2),
        tf.keras.layers.Conv2D(192, 5, padding='same', activation='relu'),  # 原256→192
        tf.keras.layers.MaxPool2D(3, strides=2),
        tf.keras.layers.Conv2D(256, 3, padding='same', activation='relu'),  # 原384→256
        tf.keras.layers.Conv2D(256, 3, padding='same', activation='relu'),
        tf.keras.layers.Conv2D(128, 3, padding='same', activation='relu'),  # 原256→128
        tf.keras.layers.MaxPool2D(3, strides=2),
        tf.keras.layers.Flatten(),
        tf.keras.layers.Dense(1024, activation='relu'),  # 原4096→1024
        tf.keras.layers.Dropout(0.5),
        tf.keras.layers.Dense(512, activation='relu'),   # 原4096→512
        tf.keras.layers.Dropout(0.5),
        tf.keras.layers.Dense(category_num, activation='softmax')
    ])
    return model
def create_data_generator(data_path, augment=False):
    """创建数据生成器"""
    if augment:
        datagen = ImageDataGenerator(
            rescale=1. / 255,
            rotation_range=20,
            width_shift_range=0.2,
            height_shift_range=0.2,
            horizontal_flip=True
        )
    else:
        datagen = ImageDataGenerator(rescale=1. / 255)

    generator = datagen.flow_from_directory(
        directory=data_path,
        target_size=image_size,
        batch_size=batch_size,
        class_mode='categorical',
        classes=categories,
        shuffle=True
    )
    return generator


def train():
    # 创建数据生成器
    train_generator = create_data_generator(train_data_path, augment=True)
    test_generator = create_data_generator(test_data_path)

    # 创建模型
    alexnet_model = create_alexnet(image_size + (3,), len(categories))
    lr = 0.0001
    adam = tf.keras.optimizers.Adam(learning_rate=lr)
    alexnet_model.compile(loss="categorical_crossentropy", optimizer=adam, metrics=["accuracy"])

    # 加载权重（如果存在）
    if os.path.exists(weights_file_path):
        alexnet_model.load_weights(weights_file_path)
        print('Weights loaded.')

    # 回调函数
    checkpoint = ModelCheckpoint(
        filepath=weights_file_path,
        monitor='val_accuracy',
        save_best_only=True,
        save_weights_only=True,
        mode='max'
    )
    early_stop = EarlyStopping(monitor='val_accuracy', patience=10, mode='max')

    # 训练模型
    history = alexnet_model.fit(
        train_generator,
        steps_per_epoch=train_generator.samples // batch_size,
        validation_data=test_generator,
        validation_steps=test_generator.samples // batch_size,
        epochs=20,
        callbacks=[checkpoint, early_stop],
        verbose=1
    )

    # 保存最终权重
    alexnet_model.save_weights(weights_file_path)


if __name__ == '__main__':
    print(weights_file_path)
    train()
