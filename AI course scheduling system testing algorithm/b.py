
import os
import cv2
import numpy as np
import tensorflow as tf
from tensorflow.keras.callbacks import ModelCheckpoint, EarlyStopping

# 配置GPU显存按需分配
gpus = tf.config.list_physical_devices('GPU')
if gpus:
    try:
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(gpu, True)
    except RuntimeError as e:
        print(e)

# 常量定义
work_dir = 'D:/Vgg16/data'
test_data_path = os.path.join(work_dir, 'test')
train_data_path = os.path.join(work_dir, 'train')
weights_file_path = os.path.join(work_dir, 'vgg19.weights.h5')
image_size = (128, 128)  # 可尝试减小尺寸如(64,64)以节省显存
categories = ['bellflower', 'coreopsis', 'iris','orchid', 'rose','sunflower','tulip']
batch_size = 32  # 减小批次大小以适应显存

# 数据加载与预处理（使用ImageDataGenerator优化内存）
train_datagen = tf.keras.preprocessing.image.ImageDataGenerator(
    rescale=1./255,
    validation_split=0.2  # 使用部分数据作为验证集
)

train_generator = train_datagen.flow_from_directory(
    train_data_path,
    target_size=image_size,
    batch_size=batch_size,
    class_mode='categorical',
    subset='training'
)

val_generator = train_datagen.flow_from_directory(
    train_data_path,
    target_size=image_size,
    batch_size=batch_size,
    class_mode='categorical',
    subset='validation'
)

# 创建简化后的模型（确保与权重文件匹配）
def create_vgg19_model(input_shape, category_num):
    model = tf.keras.Sequential([
        tf.keras.layers.InputLayer(input_shape=input_shape),
        tf.keras.layers.Conv2D(64, (3,3), activation='relu', padding='same'),
        tf.keras.layers.MaxPooling2D(2,2),
        tf.keras.layers.Conv2D(128, (3,3), activation='relu', padding='same'),
        tf.keras.layers.MaxPooling2D(2,2),
        tf.keras.layers.Flatten(),
        tf.keras.layers.Dense(256, activation='relu'),
        tf.keras.layers.Dropout(0.5),
        tf.keras.layers.Dense(category_num, activation='softmax')
    ])
    return model

# 初始化模型
model = create_vgg19_model(image_size + (3,), len(categories))
model.compile(
    optimizer=tf.keras.optimizers.Adam(learning_rate=1e-4),
    loss='categorical_crossentropy',
    metrics=['accuracy']
)

# 如果存在旧权重且结构匹配则加载
if os.path.exists(weights_file_path):
    try:
        model.load_weights(weights_file_path)
        print("Loaded existing weights.")
    except:
        print("Weight file exists but incompatible. Starting fresh training.")

# 回调函数
checkpoint = ModelCheckpoint(
    weights_file_path,
    monitor='val_accuracy',
    save_best_only=True,
    mode='max'
)
earlystop = EarlyStopping(
    monitor='val_accuracy',
    patience=10,
    restore_best_weights=True
)

# 训练模型
history = model.fit(
    train_generator,
    steps_per_epoch=train_generator.samples // batch_size,
    validation_data=val_generator,
    validation_steps=val_generator.samples // batch_size,
    epochs=50,
    callbacks=[checkpoint, earlystop]
)