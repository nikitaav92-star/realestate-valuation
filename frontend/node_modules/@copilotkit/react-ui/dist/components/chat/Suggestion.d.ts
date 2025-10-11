import * as react_jsx_runtime from 'react/jsx-runtime';
import { CopilotContextParams, CopilotMessagesContextParams, CopilotChatSuggestionConfiguration } from '@copilotkit/react-core';
import { SuggestionsProps } from './props.js';
import '@copilotkit/runtime-client-gql';

declare function Suggestion({ title, message, onClick, partial, className }: SuggestionsProps): react_jsx_runtime.JSX.Element;
declare const reloadSuggestions: (context: CopilotContextParams & CopilotMessagesContextParams, chatSuggestionConfiguration: {
    [key: string]: CopilotChatSuggestionConfiguration;
}, setCurrentSuggestions: (suggestions: {
    title: string;
    message: string;
}[]) => void, abortControllerRef: React.MutableRefObject<AbortController | null>) => Promise<void>;

export { Suggestion, reloadSuggestions };
