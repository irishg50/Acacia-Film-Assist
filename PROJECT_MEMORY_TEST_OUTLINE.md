# Project Memory Function Test Outline

## Overview
This test suite is designed to assess how well the ACACIA chatbot remembers and applies context from previous conversations within a project. The tests evaluate both short-term session memory and long-term project memory across multiple chat sessions.

## Test Environment Setup

### Prerequisites
- Create a new test project called "Memory Test Project"
- Ensure the project has no existing documents or chat history
- Have a clean user session (no previous interactions with this project)

### Test Structure
Each test should be conducted in a fresh chat session within the same project to isolate memory effects.

---

## Test Suite 1: Basic Memory Retention

### Test 1.1: Simple Fact Recall
**Objective**: Test if the system remembers basic facts mentioned in previous sessions

**Steps**:
1. **Session 1**: Tell the system: "My documentary is about climate change in the Arctic, and my main character is Dr. Sarah Chen, a marine biologist."
2. **Session 2**: Ask: "What is my documentary about and who is my main character?"
3. **Expected**: Should recall both the topic (climate change in Arctic) and character (Dr. Sarah Chen)

**Success Criteria**: 
- ✅ Correctly recalls documentary topic
- ✅ Correctly recalls character name and profession
- ⚠️ Partially recalls (one out of two)
- ❌ No recall

### Test 1.2: Project Details Memory
**Objective**: Test retention of project-specific details

**Steps**:
1. **Session 1**: "My budget is $150,000 and I'm targeting PBS for distribution. I'm shooting in Alaska for 3 weeks."
2. **Session 2**: Ask: "What are my budget, distribution target, and shooting details?"
3. **Expected**: Should recall budget, distribution target, and shooting location/duration

**Success Criteria**:
- ✅ Recalls all three details accurately
- ⚠️ Recalls 2 out of 3 details
- ❌ Recalls 1 or fewer details

---

## Test Suite 2: Decision Memory

### Test 2.1: Creative Decisions
**Objective**: Test if the system remembers creative choices and decisions

**Steps**:
1. **Session 1**: "I decided to use a vérité style with minimal narration, focusing on observational footage. I chose to shoot in 4K with a Sony FX6."
2. **Session 2**: Ask: "What shooting style and equipment decisions did we discuss?"
3. **Expected**: Should recall vérité style, minimal narration, 4K, Sony FX6

**Success Criteria**:
- ✅ Recalls all technical and creative decisions
- ⚠️ Recalls most decisions but misses some details
- ❌ Poor recall of decisions

### Test 2.2: Problem-Solving Memory
**Objective**: Test retention of problems and solutions discussed

**Steps**:
1. **Session 1**: "I'm having trouble getting permits for filming in the Arctic National Wildlife Refuge. You suggested I contact the US Fish and Wildlife Service and apply 6 months in advance."
2. **Session 2**: Ask: "What was the permit issue we discussed and what solution did you recommend?"
3. **Expected**: Should recall the permit problem and the specific solution

**Success Criteria**:
- ✅ Recalls both problem and solution accurately
- ⚠️ Recalls problem but not solution (or vice versa)
- ❌ No recall of either

---

## Test Suite 3: Contextual Continuity

### Test 3.1: Story Development Continuity
**Objective**: Test if the system maintains story development context

**Steps**:
1. **Session 1**: "I'm developing a three-act structure. Act 1 introduces the melting permafrost, Act 2 shows the impact on local communities, and Act 3 explores solutions."
2. **Session 2**: Ask: "How does my three-act structure work and what should I focus on in Act 2?"
3. **Expected**: Should recall the structure and provide specific guidance for Act 2

**Success Criteria**:
- ✅ Recalls structure and provides relevant Act 2 guidance
- ⚠️ Recalls structure but gives generic advice
- ❌ No recall of structure

### Test 3.2: Character Development Memory
**Objective**: Test retention of character development details

**Steps**:
1. **Session 1**: "Dr. Chen is struggling with the emotional toll of watching the ecosystem change. She's also dealing with funding cuts that threaten her research."
2. **Session 2**: Ask: "What are the main challenges facing Dr. Chen in my story?"
3. **Expected**: Should recall both emotional and practical challenges

**Success Criteria**:
- ✅ Recalls both emotional and practical challenges
- ⚠️ Recalls one type of challenge
- ❌ No recall of character challenges

---

## Test Suite 4: Technical Memory

### Test 4.1: Workflow Decisions
**Objective**: Test memory of technical workflow decisions

**Steps**:
1. **Session 1**: "I decided to use DaVinci Resolve for editing, Pro Tools for sound design, and I'm planning a 90-minute final cut with 5.1 surround sound."
2. **Session 2**: Ask: "What editing and post-production decisions did we make?"
3. **Expected**: Should recall software choices, duration, and audio format

**Success Criteria**:
- ✅ Recalls all technical decisions accurately
- ⚠️ Recalls most but misses some details
- ❌ Poor recall of technical decisions

### Test 4.2: Equipment and Setup Memory
**Objective**: Test retention of equipment and setup details

**Steps**:
1. **Session 1**: "I'm using a DJI Ronin 2 gimbal for smooth shots, Sennheiser MKH 416 for interviews, and I have a backup generator for power in remote locations."
2. **Session 2**: Ask: "What equipment setup did we discuss for my Arctic shoot?"
3. **Expected**: Should recall gimbal, microphone, and power solutions

**Success Criteria**:
- ✅ Recalls all equipment and setup details
- ⚠️ Recalls some equipment but misses others
- ❌ Poor recall of equipment decisions

---

## Test Suite 5: Complex Memory Integration

### Test 5.1: Multi-Session Story Arc
**Objective**: Test memory across multiple sessions with evolving story

**Steps**:
1. **Session 1**: "My documentary explores how climate change affects Arctic communities. I'm following three families over a year."
2. **Session 2**: "I decided to focus on the Inupiat community in Utqiagvik. The main family is the Ahnupka family."
3. **Session 3**: "The Ahnupka family is struggling with changing hunting patterns due to melting ice."
4. **Session 4**: Ask: "What is my documentary about and how has the story evolved?"
5. **Expected**: Should recall the overall topic, specific community, family, and current challenges

**Success Criteria**:
- ✅ Recalls complete story evolution across all sessions
- ⚠️ Recalls most elements but misses some progression
- ❌ Poor recall of story development

### Test 5.2: Problem Evolution Memory
**Objective**: Test memory of how problems and solutions evolved

**Steps**:
1. **Session 1**: "I'm having trouble getting access to film in the Arctic. You suggested contacting local communities first."
2. **Session 2**: "I contacted the Inupiat community and they're open to filming, but I need to get proper permits."
3. **Session 3**: "The permits are approved, but now I need to plan for extreme weather conditions."
4. **Session 4**: Ask: "What access challenges have we discussed and how have they evolved?"
5. **Expected**: Should recall the progression from access → permits → weather planning

**Success Criteria**:
- ✅ Recalls complete problem evolution and solutions
- ⚠️ Recalls some progression but misses steps
- ❌ Poor recall of problem evolution

---

## Test Suite 6: Memory Accuracy and Consistency

### Test 6.1: Detail Accuracy
**Objective**: Test if recalled details are accurate

**Steps**:
1. **Session 1**: "My budget is exactly $147,500, I'm shooting for 23 days, and my target audience is PBS viewers aged 45-65."
2. **Session 2**: Ask: "What are the exact numbers for my budget, shooting days, and target audience age range?"
3. **Expected**: Should recall exact numbers, not approximations

**Success Criteria**:
- ✅ Recalls exact numbers accurately
- ⚠️ Recalls approximate numbers
- ❌ Incorrect or missing numbers

### Test 6.2: Consistency Across Sessions
**Objective**: Test if information remains consistent across multiple sessions

**Steps**:
1. **Session 1**: "My documentary is called 'Melting Point' and focuses on climate change in the Arctic."
2. **Session 2**: Ask: "What is my documentary called and what is it about?"
3. **Session 3**: Ask again: "What is my documentary called and what is it about?"
4. **Expected**: Should give consistent answers across sessions

**Success Criteria**:
- ✅ Consistent information across all sessions
- ⚠️ Minor inconsistencies
- ❌ Major inconsistencies or contradictions

---

## Test Suite 7: Memory Integration with New Information

### Test 7.1: Contextual Application
**Objective**: Test if old information is properly integrated with new requests

**Steps**:
1. **Session 1**: "My documentary is about climate change in the Arctic, budget $150K, shooting vérité style."
2. **Session 2**: Ask: "Given my project details, what festivals should I target for distribution?"
3. **Expected**: Should recommend festivals appropriate for climate change documentaries with vérité style

**Success Criteria**:
- ✅ Recommendations clearly reference and build on previous context
- ⚠️ Generic recommendations that don't leverage context
- ❌ Recommendations that ignore or contradict previous context

### Test 7.2: Problem-Solving with Memory
**Objective**: Test if the system uses memory to provide better solutions

**Steps**:
1. **Session 1**: "I'm having trouble with sound recording in windy Arctic conditions. You suggested using wind protection and backup recorders."
2. **Session 2**: Ask: "I'm still having audio issues. What specific solutions should I try?"
3. **Expected**: Should build on previous advice and provide additional solutions

**Success Criteria**:
- ✅ Builds on previous advice with additional solutions
- ⚠️ Provides new solutions but doesn't reference previous advice
- ❌ Repeats previous advice without building on it

---

## Scoring System

### Overall Memory Performance Score
Calculate the average score across all tests:

- **Excellent (90-100%)**: Consistent, accurate memory across all test types
- **Good (75-89%)**: Good memory with minor gaps or inconsistencies
- **Fair (60-74%)**: Moderate memory with some significant gaps
- **Poor (Below 60%)**: Poor memory with major gaps or inaccuracies

### Memory Type Performance
Track performance by memory type:
- **Factual Memory**: Names, numbers, dates, technical details
- **Contextual Memory**: Story development, character arcs, project evolution
- **Decision Memory**: Creative choices, technical decisions, problem solutions
- **Integration Memory**: How well old information is used with new requests

---

## Test Execution Guidelines

### Timing
- Allow at least 1 hour between sessions to test true memory vs. session persistence
- Complete all tests within 1-2 weeks to ensure consistent system behavior

### Documentation
- Record exact questions asked and responses received
- Note any inconsistencies or unexpected behavior
- Document system performance issues or delays

### Analysis
- Compare memory performance across different types of information
- Identify patterns in what the system remembers vs. forgets
- Assess the quality of memory integration and application

---

## Expected Outcomes

### Optimal Performance
- Accurate recall of 90%+ of factual information
- Consistent story and context memory across sessions
- Proper integration of old information with new requests
- Contextual recommendations that build on previous discussions

### Areas of Concern
- Frequent forgetting of key project details
- Inconsistent information across sessions
- Poor integration of memory with new requests
- Generic responses that don't leverage project context

This test outline will provide a comprehensive assessment of the project memory function and help identify areas for improvement. 