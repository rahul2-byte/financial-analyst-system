import { Answer, type AnswerProps } from './Answer.js';

export type StreamingAnswerProps = AnswerProps;

/**
 * The live, not yet committed tail of a streaming answer. It draws exactly like a
 * committed `Answer`, so the text does not change shape when it is committed.
 */
export function StreamingAnswer(props: StreamingAnswerProps) {
  return <Answer {...props} />;
}
