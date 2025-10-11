import { CopilotContextParams, CopilotMessagesContextParams } from '@copilotkit/react-core';
import { CopilotKitVersion } from './types.js';

declare function shouldShowDevConsole(showDevConsole: boolean | "auto"): boolean;
declare function getPublishedCopilotKitVersion(current: string, forceCheck?: boolean): Promise<CopilotKitVersion>;
declare function logReadables(context: CopilotContextParams): void;
declare function logActions(context: CopilotContextParams): void;
declare function logMessages(context: CopilotMessagesContextParams): void;

export { getPublishedCopilotKitVersion, logActions, logMessages, logReadables, shouldShowDevConsole };
