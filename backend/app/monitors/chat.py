from dataclasses import dataclass
import re
from difflib import SequenceMatcher


@dataclass
class ViewerCommand:
    command: str
    viewer_name: str
    prompt: str
    is_streamer: bool = False


TRIGGERS = (
    '\u043d\u0435\u0439\u0440\u043e\u0437\u0435\u0442\u043a\u0430',
    '\u043d\u0435\u0439\u0440\u043e \u0437\u0435\u0442\u043a\u0430',
    '\u0437\u0435\u0442\u043e\u0447\u043a\u0430',
    '\u0437\u0435\u0442\u043a\u0430',
    '\u0437\u0435\u0442',
    'neyrozetka',
    '!askbot',
)
WAKE_WORDS = ('нейро зетка', 'нейрозетка', 'зеточка', 'зетка', 'зета', 'зет')


def extract_wake_word(text: str, wake_words: tuple[str, ...] = WAKE_WORDS) -> tuple[str, str] | None:
    normalized = re.sub(r'[^\w\s-]', ' ', (text or '').casefold(), flags=re.UNICODE)
    tokens = re.findall(r'[\w-]+', normalized)
    for index, token in enumerate(tokens):
        for wake_word in wake_words:
            wake_tokens = wake_word.split()
            candidate = ' '.join(tokens[index:index + len(wake_tokens)])
            ratio = SequenceMatcher(None, candidate, wake_word).ratio()
            if candidate == wake_word or (len(candidate) >= 4 and ratio >= 0.78):
                return wake_word, ' '.join(tokens[index + len(wake_tokens):]).strip(' ,.!?-:')
    return None


def parse_viewer_command(message: str, viewer_name: str, triggers: tuple[str, ...] = TRIGGERS) -> ViewerCommand | None:
    value = message.strip()
    normalized = re.sub(r'[^\w\s!?-]', ' ', value.casefold(), flags=re.UNICODE)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    for trigger_value in triggers:
        trigger = re.sub(r'[^\w\s!?-]', ' ', trigger_value.casefold(), flags=re.UNICODE)
        trigger = re.sub(r'\s+', ' ', trigger).strip()
        if not trigger:
            continue
        match = re.search(rf'(?<!\w){re.escape(trigger)}(?!\w)', normalized)
        if match:
            position = match.start()
            prompt = normalized[position + len(trigger):].strip(' !?,.-') or value
            return ViewerCommand(command=trigger.lstrip('!'), viewer_name=viewer_name, prompt=prompt)
    if normalized.startswith('!challenge'):
        prompt = value[len('!challenge'):].strip()
        if prompt:
            return ViewerCommand(command='challenge', viewer_name=viewer_name, prompt=prompt)
    return None
