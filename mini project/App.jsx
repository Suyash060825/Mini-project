import React, {useState} from "react";

export default function App() {
  const [file, setFile] = useState(null);
  const [transcript, setTranscript] = useState("");
  const [notes, setNotes] = useState(null);
  const [quiz, setQuiz] = useState(null);
  const [loading, setLoading] = useState(false);

  async function upload() {
    if (!file) return alert("Choose a video file first");
    setLoading(true);
    const fd = new FormData();
    fd.append("file", file);

    const resp = await fetch("http://localhost:8000/upload-video/", {method: "POST", body: fd});
    const data = await resp.json();
    setTranscript(data.transcript);
    setLoading(false);
  }

  async function makeNotes() {
    setLoading(true);
    const resp = await fetch("http://localhost:8000/generate-notes/", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({transcript}),
    });
    const data = await resp.json();
    setNotes(data);
    setLoading(false);
  }

  async function makeQuiz() {
    setLoading(true);
    const resp = await fetch("http://localhost:8000/generate-quiz/", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({notes: notes.notes || notes, num_questions: 5}),
    });
    const data = await resp.json();
    setQuiz(data.quiz || data);
    setLoading(false);
  }

  return (
    <div style={{padding:20}}>
      <h2>Video → Notes → Quiz (MVP)</h2>
      <input type="file" accept="video/*" onChange={(e)=>setFile(e.target.files[0])} />
      <button onClick={upload} disabled={loading}>Upload & Transcribe</button>
      <div style={{marginTop:10}}>
        <h4>Transcript</h4>
        <pre style={{whiteSpace:"pre-wrap", maxHeight:200, overflow:"auto"}}>{transcript}</pre>
      </div>

      <button onClick={makeNotes} disabled={!transcript || loading}>Generate Notes</button>
      {notes && (
        <div>
          <h4>Summary</h4>
          <p>{notes.summary || ""}</p>
          <h4>Notes</h4>
          <ol>
            {(notes.notes || []).map((n, i)=>(<li key={i}>{n}</li>))}
          </ol>
        </div>
      )}

      <button onClick={makeQuiz} disabled={!notes || loading}>Generate Quiz</button>
      {quiz && (
        <div>
          <h4>Quiz</h4>
          {quiz.map((q, i)=>(
            <div key={i} style={{border:"1px solid #ddd", padding:8, margin:8}}>
              <strong>{i+1}. {q.question}</strong>
              <ul>
                {q.options.map((o, idx)=>(<li key={idx}>{o}</li>))}
              </ul>
              <em>Answer: {q.options[q.answer_index]}</em>
              <p>{q.explanation}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
