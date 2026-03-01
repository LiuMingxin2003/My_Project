import webbrowser

from flask import Flask, request, render_template, jsonify, Response, send_from_directory
from openai import OpenAI, api_key
from config import API_CONFIG
from renew_config import SERVER_CONFIG
import json
import os

app = Flask(__name__)
client = OpenAI(
    api_key=SERVER_CONFIG["API"],
    base_url=API_CONFIG["base_url"]
)

# 添加favicon路由
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')


# 添加基本的安全头
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response


@app.route('/')
def home():
    #webbrowser.open("http://192.168.10.16:8080")
    return render_template('index.html')


def get_api_response(user_message, max_retries=3):
    """获取API响应，支持重试机制"""
    for attempt in range(max_retries):
        try:
            print(f"\n第{attempt + 1}次尝试获取回答")
            response = client.chat.completions.create(
                model='deepseek-reasoner',
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": user_message},
                ],
                stream=True
            )

            full_response = ""
            for chunk in response:
                if chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    yield content

            if full_response.strip():  # 如果有实际内容就返回
                print(f"\n完整回答: {full_response}\n")
                return
            else:
                print(f"\n第{attempt + 1}次尝试返回为空")

        except Exception as e:
            print(f"\n第{attempt + 1}次尝试发生错误: {str(e)}")
            if attempt == max_retries - 1:  # 最后一次尝试
                raise Exception("API多次调用失败")

    raise Exception("API返回数据为空")


@app.route('/chat', methods=['POST'])
def chat():
    try:
        user_message = request.json['message']
        print(f"\n用户问题: {user_message}")

        def generate():
            for attempt in range(3):  # 最多尝试3次
                try:
                    print(f"\n第{attempt + 1}次尝试获取回答")
                    response = client.chat.completions.create(
                        model='deepseek-reasoner',
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant."},
                            {"role": "user", "content": user_message},
                        ],
                        stream=True
                    )

                    full_response = ""
                    for chunk in response:
                        if chunk.choices[0].delta.content is not None:
                            content = chunk.choices[0].delta.content
                            full_response += content
                            print(content, end='', flush=True)
                            yield f"data: {json.dumps({'content': content})}\n\n"

                    if full_response.strip():  # 如果响应不为空，则返回
                        print(f"\n完整回答: {full_response}")
                        return
                    else:
                        print(f"\n第{attempt + 1}次尝试返回为空")

                except Exception as e:
                    print(f"\n第{attempt + 1}次尝试发生错误: {str(e)}")
                    if attempt == 2:  # 最后一次尝试失败
                        yield f"data: {json.dumps({'content': '**API返回数据为空**'})}\n\n"

            # 如果所有尝试都失败
            if not full_response.strip():
                yield f"data: {json.dumps({'content': '**API返回数据为空**'})}\n\n"

        return Response(generate(), mimetype='text/event-stream')

    except Exception as e:
        error_msg = f"发生错误: {str(e)}"
        print(error_msg)
        return jsonify({"error": error_msg}), 500


if __name__ == '__main__':
    # 修改为监听所有网络接口，设置端口为输入
    app.run(host='0.0.0.0', port=SERVER_CONFIG["port"], debug=False)
