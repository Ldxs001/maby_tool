# run-name: count_words_in_text
import ast

def count_word_in_text(text, word):
    """统计单个词在文本中的出现次数"""
    if not text or not word:
        return '无有效文本或关键词'
    try:
        return f'关键词"{word}"出现{str(text.count(word))}次'
    except Exception as e:
        return f'统计失败: {str(e)}'

def process_words(data):
    """处理多个关键词的轮询统计"""
    results = []
    
    # 识别被处理文本（非列表类型的长文本）
    for key, value in data['kv'].items():
        if not isinstance(value, list) and len(str(value)) > 50:  # 长文本判定
            text = str(value)
            break
    
    # 识别词表（列表类型）
    word_lists = []
    for key, value in data['kv'].items():
        if isinstance(value, str) and value.startswith('['):  # 列表字面量判定
            try:
                word_list = ast.literal_eval(value)
                if all(isinstance(item, str) for item in word_list):
                    word_lists.append(word_list)
            except:  # 解析失败保留原字符串
                word_lists.append([value])
    
    # 轮询统计
    for word_list in word_lists:
        for word in set(word_list):  # 去重避免重复计算
            results.append(count_word_in_text(text, word))
    
    return ' '.join(results)

def run(data):
    """汇总运行结果"""
    return process_words(data)