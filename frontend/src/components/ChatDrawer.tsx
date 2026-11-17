import React, { useState, useEffect, useRef } from 'react';
import { MessageSquare, Send, Mic, MicOff, Volume2, Sparkles, User, Bot, Loader2 } from 'lucide-react';
import type { ChatMessage } from '../types';
import { sendChatMessage } from '../api';
import {
  isSpeechRecognitionSupported,
  getSpeechRecognitionLanguage,
  speakText,
} from '../utils/speech';

interface ChatDrawerProps {
  analysisContext: Record<string, any> | null;
  language: string;
}

export const ChatDrawer: React.FC<ChatDrawerProps> = ({ analysisContext, language }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(false);

  const recognitionRef = useRef<any>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setSpeechSupported(isSpeechRecognitionSupported());
  }, []);

  // Quick Question Prompts based on active language
  const getQuickQuestions = (): string[] => {
    switch (language) {
      case 'kn':
        return [
          'ಯಾವ ಮಾರುಕಟ್ಟೆಯಲ್ಲಿ ಗರಿಷ್ಠ ನಿವ್ವಳ ಲಾಭ ಸಿಗುತ್ತದೆ?',
          'ಮಳೆಯಿಂದ ಬೆಳೆ ರಕ್ಷಣೆಗೆ ತಕ್ಷಣ ಏನು ಮಾಡಬೇಕು?',
          'ಸಾರಿಗೆ ಮತ್ತು ಸಾಗಾಟ ನಷ್ಟ ಎಷ್ಟು ಕಡಿತವಾಗುತ್ತದೆ?',
        ];
      case 'hi':
        return [
          'मेरी फसल बेचने के लिए सबसे अच्छी मंडी कौन सी है?',
          'बारिश होने पर फसल की सुरक्षा कैसे करें?',
          'परिवहन और पारगमन नुकसान कितना कटेगा?',
        ];
      case 'mr':
        return [
          'शेतमाल विक्रीसाठी कोणती बाजार समिती सर्वात फायदेशीर?',
          'पाऊस आल्यास पिकाचे नुकसान कसे टाळावे?',
          'वाहतूक खर्च व नासाडी कपात किती होईल?',
        ];
      default:
        return [
          'Which target mandi yields the highest net return?',
          'How should I protect my harvested crop from rain?',
          'What is the distance transport cost breakdown?',
        ];
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const handleSend = async (questionText: string) => {
    const text = questionText.trim();
    if (!text || !analysisContext || isLoading) return;

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      sender: 'user',
      text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputValue('');
    setIsLoading(true);

    try {
      const response = await sendChatMessage(analysisContext, text, language);
      const botMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        sender: 'assistant',
        text: response.answer,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, botMsg]);
    } catch (err: any) {
      const errorMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        sender: 'assistant',
        text: 'Sorry, I could not process your question right now. Please try again.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleListening = () => {
    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
      return;
    }

    if (!speechSupported) return;

    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    const recognition = new SpeechRecognition();
    recognition.lang = getSpeechRecognitionLanguage(language);
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onstart = () => {
      setIsListening(true);
    };

    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript;
      if (transcript) {
        setInputValue(transcript);
        handleSend(transcript);
      }
      setIsListening(false);
    };

    recognition.onerror = () => {
      setIsListening(false);
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
  };

  const handleSpeakReply = (text: string) => {
    speakText(text, language);
  };

  return (
    <div className="bg-white rounded-2xl shadow-xs border border-slate-200/80 p-4 sm:p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center">
            <MessageSquare className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900">
              Interactive Regional Voice & Text Q&A
            </h3>
            <p className="text-xs text-slate-500">
              Ask follow-up questions about weather precautions, mandi quotes, or transport routes
            </p>
          </div>
        </div>

        {speechSupported && (
          <span className="text-[11px] text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200 hidden sm:inline">
            Voice STT & TTS Active
          </span>
        )}
      </div>

      {/* Quick Question Chips */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {getQuickQuestions().map((q, idx) => (
          <button
            key={idx}
            onClick={() => handleSend(q)}
            disabled={isLoading || !analysisContext}
            className="text-xs px-3 py-1.5 rounded-lg bg-slate-50 hover:bg-emerald-50 text-slate-700 hover:text-emerald-800 border border-slate-200 hover:border-emerald-300 transition cursor-pointer text-left disabled:opacity-50"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Messages Scroll Area */}
      <div className="bg-slate-50 rounded-xl p-3 h-64 overflow-y-auto border border-slate-200/80 mb-3 space-y-3">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center text-slate-400 p-4">
            <Sparkles className="w-8 h-8 mb-2 text-slate-300" />
            <p className="text-xs font-medium text-slate-600">
              No questions asked yet
            </p>
            <p className="text-[11px] text-slate-400 max-w-sm mt-1">
              Select one of the suggestion chips above or type/speak your question in{' '}
              {language.toUpperCase()}
            </p>
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex gap-2.5 ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {msg.sender === 'assistant' && (
                <div className="w-7 h-7 rounded-full bg-emerald-600 text-white flex items-center justify-center shrink-0 text-xs">
                  <Bot className="w-4 h-4" />
                </div>
              )}

              <div
                className={`max-w-[80%] rounded-xl p-3 text-xs leading-relaxed ${
                  msg.sender === 'user'
                    ? 'bg-emerald-600 text-white shadow-2xs'
                    : 'bg-white text-slate-800 border border-slate-200 shadow-2xs'
                }`}
              >
                <p>{msg.text}</p>
                <div className="flex items-center justify-between gap-3 mt-1.5 pt-1 border-t border-black/5">
                  <span className={`text-[10px] ${msg.sender === 'user' ? 'text-emerald-100' : 'text-slate-400'}`}>
                    {msg.timestamp}
                  </span>
                  {msg.sender === 'assistant' && (
                    <button
                      onClick={() => handleSpeakReply(msg.text)}
                      className="text-emerald-700 hover:text-emerald-800 flex items-center gap-1 font-semibold text-[10px] cursor-pointer"
                      title="Listen to this reply"
                    >
                      <Volume2 className="w-3 h-3" />
                      <span>Listen</span>
                    </button>
                  )}
                </div>
              </div>

              {msg.sender === 'user' && (
                <div className="w-7 h-7 rounded-full bg-slate-300 text-slate-700 flex items-center justify-center shrink-0 text-xs">
                  <User className="w-4 h-4" />
                </div>
              )}
            </div>
          ))
        )}

        {isLoading && (
          <div className="flex items-center gap-2 text-xs text-slate-500 bg-white p-2.5 rounded-xl border border-slate-200 w-fit">
            <Loader2 className="w-3.5 h-3.5 animate-spin text-emerald-600" />
            <span>Consulting KrishiSetu Advisor...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Bar with Mic */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleSend(inputValue);
        }}
        className="flex items-center gap-2"
      >
        <div className="relative flex-1">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder={
              language === 'kn'
                ? 'ಪ್ರಶ್ನೆ ಕೇಳಿ (ಉದಾ. ಮಳೆ ರಕ್ಷಣೆ ಹೇಗೆ?)...'
                : language === 'hi'
                ? 'प्रश्न पूछें (उदा. बारिश से बचाव कैसे करें?)...'
                : language === 'mr'
                ? 'प्रश्न विचारा (उदा. पिकाचे रक्षण कसे करावे?)...'
                : 'Ask a question in your regional language...'
            }
            disabled={isLoading || !analysisContext}
            className="w-full pl-3 pr-10 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:outline-hidden focus:ring-2 focus:ring-emerald-500 focus:bg-white text-slate-800 disabled:opacity-50 transition"
          />

          {/* Mic Button */}
          {speechSupported && (
            <button
              type="button"
              onClick={toggleListening}
              disabled={isLoading || !analysisContext}
              className={`absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-lg transition cursor-pointer ${
                isListening
                  ? 'bg-rose-600 text-white animate-pulse'
                  : 'text-slate-400 hover:text-emerald-600'
              }`}
              title={isListening ? 'Stop Listening' : `Speak in ${language.toUpperCase()}`}
            >
              {isListening ? <MicOff className="w-3.5 h-3.5" /> : <Mic className="w-3.5 h-3.5" />}
            </button>
          )}
        </div>

        <button
          type="submit"
          disabled={!inputValue.trim() || isLoading || !analysisContext}
          className="p-2.5 bg-emerald-600 hover:bg-emerald-700 active:bg-emerald-800 text-white rounded-xl transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
          title="Send query"
        >
          <Send className="w-4 h-4" />
        </button>
      </form>
    </div>
  );
};
