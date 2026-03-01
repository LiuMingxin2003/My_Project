
import os
from random import shuffle
import tensorflow.keras.backend as k
import cv2
import numpy as np
import tensorflow as tf
from tensorflow.keras.callbacks import ModelCheckpoint, EarlyStopping


# 设置图片通道类型
k.set_image_data_format('channels_last')

work_dir = 'D:/Vgg16/data'
test_data_path = os.path.join(work_dir, 'test')
train_data_path = os.path.join(work_dir, 'train')
predict_data_path = os.path.join(work_dir, 'D:\Vital\VGGNet\data\predict')
categories = os.listdir(train_data_path)

if not os.path.exists(work_dir ):
    os.mkdir(work_dir )
weights_file_path = os.path.join(work_dir, 'vgg19.weights.h5')
image_size = (128, 128)
categories = ['bellflower', 'coreopsis', 'iris','orchid', 'rose','sunflower','tulip']

def load_data(data_path):
        image_file_list = []
        for category in categories:
            category_path = os.path.join(data_path, category)
            for image_path in os.listdir(category_path):
                image_file_list.append(os.path.join(category_path, image_path))

        shuffle(image_file_list)
        image_list, label_list, label_idx_list = [], [], []
        for image_path in image_file_list:
            image = cv2.imread(image_path)
            image_list.append(image)

            os_name = os.name
            if os_name == 'nt':
                image_label = image_path.split('\\')[-2]
            elif os_name == 'posix':
                image_label = image_path.split('/')[-2]
            label_list.append(image_label)
            label_idx_list.append(categories.index(image_label))

        return image_list, label_idx_list, label_list

x_train, y_train, y_train_label_list = load_data(train_data_path)
x_test, y_test, y_test_label_list = load_data(test_data_path)

def batch_resize(source_image_list, image_size, normalization=True):
    target_image_list = []
    index = 0
    for image in source_image_list:
        resize_image = cv2.resize(image, image_size, interpolation=cv2.INTER_LANCZOS4)
        if normalization:
            # 将图片列表转化为图片数组，再归一化（将图像的各像素值归一化到0~1区间）
            resize_image = np.array(resize_image, dtype='float32') / 255.0
        target_image_list.append(resize_image)
        index += 1

    return np.array(target_image_list)

def one_hot_encode(label_list, classes_num):
    target_label_list = []
    for label in label_list:
        one_hot_label = np.zeros((classes_num,), dtype='float32')
        one_hot_label[label] = 1
        target_label_list.append(one_hot_label)
    return np.array(target_label_list)

def create_vgg19_model(input_shape, category_num):
    return tf.keras.models.Sequential(
        [
            tf.keras.layers.InputLayer(input_shape=input_shape),
            tf.keras.layers.Conv2D(64, (3, 3), strides=1, activation='relu', padding='same'),
            tf.keras.layers.Conv2D(64, (3, 3), strides=1, activation='relu', padding='same'),
            tf.keras.layers.MaxPooling2D(pool_size=(2, 2), strides=2),

            tf.keras.layers.Conv2D(128, (3, 3), strides=1, activation='relu', padding='same'),
            tf.keras.layers.Conv2D(128, (3, 3), strides=1, activation='relu', padding='same'),
            tf.keras.layers.MaxPooling2D(pool_size=(2, 2), strides=2),

            tf.keras.layers.Conv2D(256, (3, 3), strides=1, activation='relu', padding='same'),
            tf.keras.layers.Conv2D(256, (3, 3), strides=1, activation='relu', padding='same'),
            tf.keras.layers.Conv2D(256, (3, 3), strides=1, activation='relu', padding='same'),
            tf.keras.layers.Conv2D(256, (3, 3), strides=1, activation='relu', padding='same'),
            tf.keras.layers.MaxPooling2D(pool_size=(2, 2), strides=2),

            tf.keras.layers.Conv2D(512, (3, 3), strides=1, activation='relu', padding='same'),
            tf.keras.layers.Conv2D(512, (3, 3), strides=1, activation='relu', padding='same'),
            tf.keras.layers.Conv2D(512, (3, 3), strides=1, activation='relu', padding='same'),
            tf.keras.layers.Conv2D(512, (3, 3), strides=1, activation='relu', padding='same'),
            tf.keras.layers.MaxPooling2D(pool_size=(2, 2), strides=2),

            tf.keras.layers.Conv2D(512, (3, 3), strides=1, activation='relu', padding='same'),
            tf.keras.layers.Conv2D(512, (3, 3), strides=1, activation='relu', padding='same'),
            tf.keras.layers.Conv2D(512, (3, 3), strides=1, activation='relu', padding='same'),
            tf.keras.layers.Conv2D(512, (3, 3), strides=1, activation='relu', padding='same'),

            tf.keras.layers.MaxPooling2D(pool_size=(2, 2), strides=2),
            tf.keras.layers.Flatten(),
            tf.keras.layers.Dense(4096, activation='relu'),
            tf.keras.layers.Dropout(0.4),
            tf.keras.layers.Dense(4096, activation='relu'),
            tf.keras.layers.Dropout(0.4),
            tf.keras.layers.Dense(category_num, activation='softmax')
        ]
    )

def train():
    x_train, y_train, y_train_label_list = load_data(train_data_path)
    x_test, y_test, y_test_label_list = load_data(test_data_path)
    # 调整图片尺寸
    x_train = batch_resize(x_train, image_size, normalization=True)
    x_test = batch_resize(x_test, image_size, normalization=True)
    # 对图片标签进行one_hot编码
    y_train = one_hot_encode(y_train, len(categories))
    y_test = one_hot_encode(y_test, len(categories))

    vgg19_model = create_vgg19_model(image_size + (3,), len(categories))
    # 优化算法学习率
    lr = 0.0001
    adam = tf.keras.optimizers.Adam(learning_rate=lr)
    vgg19_model.compile(loss="categorical_crossentropy", optimizer=adam, metrics=["accuracy"])
    if os.path.exists(weights_file_path):
        vgg19_model.load_weights(weights_file_path)
        print('Weights is loaded.')
    else:
        print('Weights is not exist.')
    # 模型验证精度提升时保存模型权重
    checkpoint = ModelCheckpoint(
        filepath=weights_file_path,
        monitor='val_accuracy',
        verbose=1,
        save_best_only=True,
        save_weights_only=True,
        mode='auto',
        save_freq='epoch')
    #  模型训练提前退出回调
    earlyStopping = EarlyStopping(
        monitor='val_accuracy',
        min_delta=0,
        patience=5,
        verbose=1,
        mode='auto'
    )
    # 模型训练
    history = vgg19_model.fit(x=x_train, y=y_train,
                             batch_size=64,
                             validation_data=(x_test, y_test),
                             validation_split=0.0,
                             callbacks=[earlyStopping, checkpoint],
                             epochs=20,
                             shuffle=True,
                             verbose=1)
    # 保存训练得到的模型权重数据
    vgg19_model.save_weights(os.path.join(work_dir, 'vgg19.weights.h5'))

def evaluate_model(x_test, y_test):
    vgg19_model = create_vgg19_model(image_size + (3,), len(categories))
    lr = 0.0001
    adam = tf.keras.optimizers.Adam(learning_rate=lr)
    vgg19_model.compile(loss="categorical_crossentropy", optimizer=adam, metrics=["accuracy"])
    vgg19_model.load_weights(weights_file_path)
    loss, accuracy = vgg19_model.evaluate(x_test, y_test, verbose=1)
    print("Loss: {} --- Accuracy: {}".format(loss, accuracy))

def predict_model(x_test):
    vgg19_model = create_vgg19_model(image_size + (3,), len(categories))
    lr = 0.0001
    adam = tf.keras.optimizers.Adam(learning_rate=lr)
    vgg19_model.compile(loss="categorical_crossentropy", optimizer=adam, metrics=["accuracy"])
    vgg19_model.load_weights(weights_file_path)
    predict_score_list = vgg19_model.predict(x_test)

    predict_label_list = []
    for predict_score in predict_score_list:
        max_score_index = np.argmax(predict_score)  # 获取最大分数的索引
        predict_label_list.append(categories[max_score_index])

    print(predict_label_list)


if __name__ == '__main__':
    # 模型训练
    train()

