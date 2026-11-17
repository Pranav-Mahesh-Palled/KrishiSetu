import { fetchTTSAudio } from '../api';

let currentAudio: HTMLAudioElement | null = null;

const LANG_VOICE_TAGS: Record<string, string[]> = {
  kn: ['kn-IN', 'kn', 'kannada'],
  hi: ['hi-IN', 'hi', 'hindi'],
  mr: ['mr-IN', 'mr', 'marathi'],
  en: ['en-IN', 'en-US', 'en-GB', 'en'],
};

export function stopSpeaking(): void {
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    window.speechSynthesis.cancel();
  }
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.currentTime = 0;
    currentAudio = null;
  }
}

export async function speakText(
  text: string,
  language: string,
  callbacks?: {
    onStart?: () => void;
    onEnd?: () => void;
    onError?: (err: any) => void;
  }
): Promise<void> {
  stopSpeaking();
  const langKey = (language || 'en').toLowerCase().trim();

  // Try browser SpeechSynthesis first if native voices exist
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    const voices = window.speechSynthesis.getVoices();
    const tags = LANG_VOICE_TAGS[langKey] || ['en'];

    const matchedVoice = voices.find(v => {
      const vLang = v.lang.toLowerCase();
      const vName = v.name.toLowerCase();
      return tags.some(tag => vLang.includes(tag.toLowerCase()) || vName.includes(tag.toLowerCase()));
    });

    // Native regional voice available in browser
    if (matchedVoice) {
      try {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.voice = matchedVoice;
        utterance.lang = matchedVoice.lang;
        utterance.rate = 0.95;

        utterance.onstart = () => callbacks?.onStart?.();
        utterance.onend = () => callbacks?.onEnd?.();
        utterance.onerror = () => {
          // If browser speech synthesis encounters an error, fall back to backend TTS
          fallbackToBackendTTS(text, langKey, callbacks);
        };

        window.speechSynthesis.speak(utterance);
        return;
      } catch (e) {
        // Fallback
      }
    }
  }

  // Fallback to backend gTTS streaming endpoint
  await fallbackToBackendTTS(text, langKey, callbacks);
}

async function fallbackToBackendTTS(
  text: string,
  language: string,
  callbacks?: {
    onStart?: () => void;
    onEnd?: () => void;
    onError?: (err: any) => void;
  }
) {
  try {
    callbacks?.onStart?.();
    const blob = await fetchTTSAudio(text, language);
    const audioUrl = URL.createObjectURL(blob);
    const audio = new Audio(audioUrl);
    currentAudio = audio;

    audio.onended = () => {
      callbacks?.onEnd?.();
      currentAudio = null;
      URL.revokeObjectURL(audioUrl);
    };

    audio.onerror = (err) => {
      callbacks?.onError?.(err);
      callbacks?.onEnd?.();
      currentAudio = null;
    };

    await audio.play();
  } catch (err) {
    callbacks?.onError?.(err);
    callbacks?.onEnd?.();
  }
}

export function isSpeechRecognitionSupported(): boolean {
  if (typeof window === 'undefined') return false;
  return 'webkitSpeechRecognition' in window || 'SpeechRecognition' in window;
}

export function getSpeechRecognitionLanguage(language: string): string {
  const map: Record<string, string> = {
    kn: 'kn-IN',
    hi: 'hi-IN',
    mr: 'mr-IN',
    en: 'en-IN',
  };
  return map[language] || 'en-IN';
}
