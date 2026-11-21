import { memo } from 'react';

import { Answer, type AnswerProps } from './Answer.js';

export type StreamingAnswerProps = AnswerProps;

/**
 * The live, not yet committed tail of a streaming answer. It draws exactly like a
 * committed `Answer`, so the text does not change shape when it is committed.
 * Memoized by props: the markdown is only lexed and laid out again when the text changes.
 */
export const StreamingAnswer = memo(function StreamingAnswer(props: StreamingAnswerProps) {
  return <Answer {...props} />;
});
