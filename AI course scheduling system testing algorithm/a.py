import gc
import os
from random import shuffle
import tensorflow.keras.backend as k
import cv2
import numpy as np
import tensorflow as tf
from tensorflow.keras.callbacks import ModelCheckpoint, EarlyStopping
from tensorflow.keras.layers import GlobalAveragePooling2D, Multiply, Dense, Reshape

# 设置图片通道类型
k.set_image_data_format('channels_last')

work_dir = 'D:/Vgg16/data'
test_data_path = os.path.join(work_dir, 'test')
train_data_path = os.path.join(work_dir, 'train')
predict_data_path = os.path.join(work_dir, 'predict')  # 修正路径
weights_file_path = os.path.join(work_dir, 'vgg19.weights.h5')
image_size = (64, 64)
categories = ['bellflower', 'coreopsis', 'iris', 'orchid', 'rose', 'sunflower', 'tulip']


def load_data(data_path):
    image_file_list = []
    for category in categories:
        category_path = os.path.join(data_path, category)
        for image_path in os.listdir(category_path):
            full_path = os.path.join(category_path, image_path)
            if os.path.getsize(full_path) > 0:  # 过滤空文件
                image_file_list.append(full_path)

    shuffle(image_file_list)
    image_list, label_list, label_idx_list = [], [], []

    for image_path in image_file_list:
        try:
            # 使用IMREAD_REDUCED_COLOR_2模式加载缩小图像
            image = cv2.imread(image_path, cv2.IMREAD_REDUCED_COLOR_2)
            if image is not None:
                image_list.append(image)
                label = os.path.basename(os.path.dirname(image_path))
                label_idx_list.append(categories.index(label))
        except Exception as e:
            print(f"跳过损坏文件: {image_path} - {str(e)}")
            continue

    return image_list, label_idx_list, label_list
def batch_resize(source_image_list, image_size, normalization=True):
    return np.array([cv2.resize(img, image_size) / 255.0 for img in source_image_list],
                    dtype=np.float32)


def one_hot_encode(label_list, classes_num):
    return np.eye(classes_num, dtype=np.float32)[label_list]


class SEBlock(tf.keras.layers.Layer):
    def __init__(self, ratio=16, **kwargs):
        super().__init__(**kwargs)
        self.ratio = ratio

    def build(self, input_shape):
        self.channels = input_shape[-1]
        self.se_dense = tf.keras.Sequential([
            GlobalAveragePooling2D(),
            Dense(self.channels // self.ratio, activation='relu'),
            Dense(self.channels, activation='sigmoid'),
            Reshape((1, 1, self.channels))
        ])
        super().build(input_shape)

    def call(self, inputs):
        return Multiply()([inputs, self.se_dense(inputs)])

    def get_config(self):
        return {'ratio': self.ratio}


def create_vgg19_model(input_shape, category_num):
    model = tf.keras.Sequential([
        # Block 1
        tf.keras.layers.Conv2D(64, (3,3), activation='relu', padding='same', input_shape=input_shape),
        tf.keras.layers.Conv2D(64, (3,3), activation='relu', padding='same'),
        SEBlock(),
        tf.keras.layers.MaxPooling2D(2, strides=2),

        # Block 2
        tf.keras.layers.Conv2D(128, (3, 3), activation='relu', padding='same'),
        tf.keras.layers.Conv2D(128, (3, 3), activation='relu', padding='same'),
        SEBlock(),  # 添加SE注意力
        tf.keras.layers.MaxPooling2D((2, 2), strides=2),

        # Block 3
        tf.keras.layers.Conv2D(256, (3, 3), activation='relu', padding='same'),
        tf.keras.layers.Conv2D(256, (3, 3), activation='relu', padding='same'),
        tf.keras.layers.Conv2D(256, (3, 3), activation='relu', padding='same'),
        tf.keras.layers.Conv2D(256, (3, 3), activation='relu', padding='same'),
        SEBlock(),  # 添加SE注意力
        tf.keras.layers.MaxPooling2D((2, 2), strides=2),

         # Block 4
        tf.keras.layers.Conv2D(512, (3, 3), activation='relu', padding='same'),
        tf.keras.layers.Conv2D(512, (3, 3), activation='relu', padding='same'),
        tf.keras.layers.Conv2D(512, (3, 3), activation='relu', padding='same'),
        tf.keras.layers.Conv2D(512, (3, 3), activation='relu', padding='same'),
        SEBlock(),  # 添加SE注意力
        tf.keras.layers.MaxPooling2D((2, 2), strides=2),

        # Block 5
        tf.keras.layers.Conv2D(512, (3, 3), activation='relu', padding='same'),
        tf.keras.layers.Conv2D(512, (3, 3), activation='relu', padding='same'),
        tf.keras.layers.Conv2D(512, (3, 3), activation='relu', padding='same'),
        tf.keras.layers.Conv2D(512, (3, 3), activation='relu', padding='same'),
        SEBlock(),  # 添加SE注意力
        tf.keras.layers.MaxPooling2D((2, 2), strides=2),

        tf.keras.layers.Flatten(),
        tf.keras.layers.Dense(4096, activation='relu'),
        tf.keras.layers.Dropout(0.4),
        tf.keras.layers.Dense(4096, activation='relu'),
        tf.keras.layers.Dropout(0.4),
        tf.keras.layers.Dense(category_num, activation='softmax')
    ])
    model.build(input_shape=(None, *input_shape))  # 关键修复
    return model


def train():
    # ==== 新增：清理旧权重 ====
    if os.path.exists(weights_file_path):
        os.remove(weights_file_path)
        print(f"已清理旧权重文件: {weights_file_path}")

    # ==== 数据加载和预处理 ====
    x_train, y_train, _ = load_data(train_data_path)
    x_test, y_test, _ = load_data(test_data_path)
    x_train = batch_resize(x_train, image_size)
    x_test = batch_resize(x_test, image_size)
    y_train = one_hot_encode(y_train, len(categories))
    y_test = one_hot_encode(y_test, len(categories))

    # ==== 模型构建 ====
    model = create_vgg19_model(image_size + (3,), len(categories))

    # ==== 迁移学习设置 ====
    for layer in model.layers[:17]:
        layer.trainable = False

    # ==== 编译模型 ====
    model.compile(optimizer=tf.keras.optimizers.Adam(1e-5),
                  loss='categorical_crossentropy',
                  metrics=['accuracy'])

    # ==== 回调设置 ====
    checkpoint = ModelCheckpoint(
        filepath=weights_file_path,
        monitor='val_accuracy',
        save_best_only=True,
        save_weights_only=True,
        mode='max',
        verbose=1
    )
    early_stop = EarlyStopping(monitor='val_accuracy', patience=15)

    # ==== 第一阶段训练 ====
    print("\n=== 第一阶段训练 ===")
    history = model.fit(
        x_train, y_train,
        validation_data=(x_test, y_test),
        epochs=250,
        batch_size=32,
        callbacks=[checkpoint, early_stop],
        verbose=1
    )

    # ==== 全层微调 ====
    print("\n=== 全层微调 ===")
    for layer in model.layers:
        layer.trainable = True
    model.compile(optimizer=tf.keras.optimizers.Adam(1e-6),
                  loss='categorical_crossentropy',
                  metrics=['accuracy'])

    history = model.fit(
        x_train, y_train,
        validation_data=(x_test, y_test),
        epochs=60,
        batch_size=32,
        callbacks=[checkpoint],  # 继续使用相同的checkpoint
        verbose=1
    )
    tf.keras.backend.clear_session()
    gc.collect()  # 需要import gc
    return x_train, x_test, y_train, y_test


def evaluate_model(x_test, y_test):  # 接收预处理后的数据
    # 构建模型
    model = create_vgg19_model(image_size + (3,), len(categories))
    model.load_weights(weights_file_path)
    model.compile(loss='categorical_crossentropy',
                  optimizer='adam',
                  metrics=['accuracy'])

    # 分批评估
    batch_size = 64
    steps = len(x_test) // batch_size
    if steps == 0:
        steps = 1

    # 使用evaluate的generator模式
    loss, acc = model.evaluate(
        tf.data.Dataset.from_tensor_slices((x_test, y_test)).batch(batch_size),
        steps=steps,
        verbose=1
    )
    print(f'测试准确率: {acc:.2%}')


if __name__ == '__main__':
    # 训练阶段
    x_train, x_test, y_train, y_test = train()  # 修改train()返回预处理数据

    # 立即释放训练数据内存
    del x_train, y_train

    # 评估阶段
    evaluate_model(x_test, y_test)

    # 最终释放内存
    del x_test, y_test
    tf.keras.backend.clear_session()