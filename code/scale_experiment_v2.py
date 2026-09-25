#!/usr/bin/env python3
"""
Cross-Framework Variance Decomposition at Scale (6, 8, 10, 12 qubits).
v2: Uses westquant-bridges benchmark generators where available.
    Fixes Grover on Cirq (was broken due to TOFFOLI multi-qubit issue).
"""
import warnings
warnings.filterwarnings("ignore")
import json
import time
import numpy as np
from collections import defaultdict

# ===========================================================================
# Framework imports
# ===========================================================================
from westquant_qiskit import DeterministicSearchEngine, SearchSpace as QiskitSS
from westquant_pytket import PytketSequentialSearch
from westquant_pennylane import PennyLaneSequentialSearch
from westquant_bridges import (
    CirqSequentialSearch,
    grover_circuit_cirq, ghz_circuit_cirq,
    grover_circuit_qiskit, ghz_circuit_qiskit,
)

# ===========================================================================
# Benchmark circuit generators (from westquant-bridges)
# ===========================================================================
def qft_circuit_qiskit(n):
    from qiskit.circuit.library import QFT
    return QFT(num_qubits=n).decompose()

def qft_circuit_cirq(n):
    import cirq
    qubits = sorted(cirq.LineQubit.range(n))
    circuit = cirq.Circuit()
    for i in range(n): circuit.append(cirq.H(qubits[i]))
    for i in range(n):
        for j in range(i + 1, n):
            circuit.append(cirq.CZ(qubits[j], qubits[i]) ** (1.0 / (2 ** (j - i))))
    return circuit

# QPE, BV, Superposition (custom, not in benchmarks yet)
def qpe_circuit_qiskit(n):
    from qiskit import QuantumCircuit, QuantumRegister
    from qiskit.circuit.library import QFT
    n_counting = n - 1
    qr = QuantumRegister(n, 'q')
    qc = QuantumCircuit(qr, name=f"QPE_{n_counting}")
    counting = list(range(1, n))
    qc.x(0)
    for i in counting: qc.h(i)
    repetitions = 1
    for c in counting:
        for _ in range(repetitions):
            qc.cp(np.pi / 2, c, 0)
        repetitions *= 2
    qft_inv = QFT(num_qubits=n_counting).inverse().decompose()
    qc.compose(qft_inv, qubits=counting, inplace=True)
    return qc

def qpe_circuit_cirq(n):
    import cirq
    n_counting = n - 1
    qubits = sorted(cirq.LineQubit.range(n))
    circuit = cirq.Circuit()
    counting = qubits[1:]
    circuit.append(cirq.X(qubits[0]))
    for i in counting: circuit.append(cirq.H(i))
    repetitions = 1
    for c in counting:
        for _ in range(repetitions):
            circuit.append(cirq.CZ(c, qubits[0]) ** 0.25)
        repetitions *= 2
    for i in range(len(counting)):
        circuit.append(cirq.H(counting[i]))
        for j in range(i + 1, len(counting)):
            circuit.append(cirq.CZ(counting[j], counting[i]) ** (-1.0 / (2 ** (j - i))))
    return circuit

def bv_circuit_qiskit(n):
    from qiskit import QuantumCircuit
    n_input = n - 1
    qc = QuantumCircuit(n, name=f"BV_{n_input}")
    qc.x(n_input)
    for i in range(n): qc.h(i)
    secret = "1011"[:n_input].ljust(n_input, '1')
    for i, bit in enumerate(secret):
        if bit == '1': qc.cx(i, n_input)
    for i in range(n): qc.h(i)
    return qc

def bv_circuit_cirq(n):
    import cirq
    n_input = n - 1
    qubits = sorted(cirq.LineQubit.range(n))
    circuit = cirq.Circuit()
    circuit.append(cirq.X(qubits[n_input]))
    for i in range(n): circuit.append(cirq.H(qubits[i]))
    secret = "1011"[:n_input].ljust(n_input, '1')
    for i, bit in enumerate(secret):
        if bit == '1': circuit.append(cirq.CNOT(qubits[i], qubits[n_input]))
    for i in range(n): circuit.append(cirq.H(qubits[i]))
    return circuit

def superposition_circuit_qiskit(n, k=2):
    from qiskit import QuantumCircuit
    qc = QuantumCircuit(n, name=f"Superposition_{n}")
    for i in range(n): qc.h(i)
    for i in range(min(k, n-1)): qc.cx(i, i+1)
    return qc

def superposition_circuit_cirq(n, k=2):
    import cirq
    qubits = sorted(cirq.LineQubit.range(n))
    circuit = cirq.Circuit()
    for i in range(n): circuit.append(cirq.H(qubits[i]))
    for i in range(min(k, n-1)): circuit.append(cirq.CNOT(qubits[i], qubits[i+1]))
    return circuit

# PennyLane generators
def pennylane_qft(n):
    import pennylane as qml
    import numpy as np
    dev = qml.device('lightning.qubit', wires=n)
    @qml.qnode(dev)
    def circuit():
        for i in range(n): qml.Hadamard(wires=i)
        for i in range(n):
            for j in range(i + 1, n):
                qml.ControlledPhaseShift(np.pi / (2 ** (j - i)), wires=[j, i])
        return qml.state()
    return circuit.construct((), {})

def pennylane_grover(n, marked=0):
    import pennylane as qml
    dev = qml.device('lightning.qubit', wires=n)
    @qml.qnode(dev)
    def circuit():
        for i in range(n): qml.Hadamard(wires=i)
        binary = format(marked, f'0{n}b')
        for i, bit in enumerate(binary):
            if bit == '0': qml.PauliX(wires=i)
        qml.Hadamard(wires=n-1)
        qml.MultiControlledX(wires=list(range(n-1)) + [n-1])
        qml.Hadamard(wires=n-1)
        for i, bit in enumerate(binary):
            if bit == '0': qml.PauliX(wires=i)
        for i in range(n): qml.Hadamard(wires=i)
        for i in range(n): qml.PauliX(wires=i)
        qml.Hadamard(wires=n-1)
        qml.MultiControlledX(wires=list(range(n-1)) + [n-1])
        qml.Hadamard(wires=n-1)
        for i in range(n): qml.PauliX(wires=i)
        for i in range(n): qml.Hadamard(wires=i)
        return qml.state()
    return circuit.construct((), {})

def pennylane_ghz(n):
    import pennylane as qml
    dev = qml.device('lightning.qubit', wires=n)
    @qml.qnode(dev)
    def circuit():
        qml.Hadamard(wires=0)
        for i in range(n - 1): qml.CNOT(wires=[i, i + 1])
        return qml.state()
    return circuit.construct((), {})

def pennylane_qpe(n):
    import pennylane as qml
    import numpy as np
    n_counting = n - 1
    dev = qml.device('lightning.qubit', wires=n)
    @qml.qnode(dev)
    def circuit():
        qml.PauliX(wires=0)
        for i in range(1, n): qml.Hadamard(wires=i)
        repetitions = 1
        for c in range(1, n):
            for _ in range(repetitions):
                qml.ControlledPhaseShift(np.pi / 2, wires=[c, 0])
            repetitions *= 2
        for i in range(1, n):
            qml.Hadamard(wires=i)
            for j in range(i + 1, n):
                qml.ControlledPhaseShift(-np.pi / (2 ** (j - i)), wires=[j, i])
        return qml.state()
    return circuit.construct((), {})

def pennylane_bv(n):
    import pennylane as qml
    n_input = n - 1
    dev = qml.device('lightning.qubit', wires=n)
    @qml.qnode(dev)
    def circuit():
        qml.PauliX(wires=n_input)
        for i in range(n): qml.Hadamard(wires=i)
        secret = "1011"[:n_input].ljust(n_input, '1')
        for i, bit in enumerate(secret):
            if bit == '1': qml.CNOT(wires=[i, n_input])
        for i in range(n): qml.Hadamard(wires=i)
        return qml.state()
    return circuit.construct((), {})

def pennylane_superposition(n, k=2):
    import pennylane as qml
    dev = qml.device('lightning.qubit', wires=n)
    @qml.qnode(dev)
    def circuit():
        for i in range(n): qml.Hadamard(wires=i)
        for i in range(min(k, n-1)): qml.CNOT(wires=[i, i+1])
        return qml.state()
    return circuit.construct((), {})

# ===========================================================================
# Circuit generator registry
# ===========================================================================
CIRCUIT_GENERATORS = {
    "QFT": {"qiskit": qft_circuit_qiskit, "cirq": qft_circuit_cirq,
            "pennylane": pennylane_qft, "pytket": "qiskit_convert"},
    "Grover": {"qiskit": grover_circuit_qiskit, "cirq": grover_circuit_cirq,
               "pennylane": pennylane_grover, "pytket": "qiskit_convert"},
    "QPE": {"qiskit": qpe_circuit_qiskit, "cirq": qpe_circuit_cirq,
            "pennylane": pennylane_qpe, "pytket": "qiskit_convert"},
    "GHZ": {"qiskit": ghz_circuit_qiskit, "cirq": ghz_circuit_cirq,
            "pennylane": pennylane_ghz, "pytket": "qiskit_convert"},
    "BV": {"qiskit": bv_circuit_qiskit, "cirq": bv_circuit_cirq,
           "pennylane": pennylane_bv, "pytket": "qiskit_convert"},
    "Superposition": {"qiskit": superposition_circuit_qiskit, "cirq": superposition_circuit_cirq,
                      "pennylane": pennylane_superposition, "pytket": "qiskit_convert"},
}

# ===========================================================================
# Experiment configuration
# ===========================================================================
QUBIT_SIZES = [6, 8, 10, 12]
ALGORITHMS = ["QFT", "Grover", "QPE", "GHZ", "BV", "Superposition"]
N_REPLICATES = 3
SEEDS = list(range(42, 42 + N_REPLICATES))

print("=" * 80)
print("Cross-Framework Variance Decomposition at Scale (v2)")
print("=" * 80)
print(f"Qubit sizes: {QUBIT_SIZES}")
print(f"Algorithms: {ALGORITHMS}")
print(f"Replicates: {N_REPLICATES}")
print(f"Frameworks: Qiskit, Pytket, PennyLane, Cirq")
print(f"Using benchmark generators from westquant-bridges for GHZ/Grover/QFT")
print()

# ===========================================================================
# Run experiments
# ===========================================================================
all_observations = []
timing_data = defaultdict(dict)

for n_qubits in QUBIT_SIZES:
    print(f"\n{'#'*80}")
    print(f"# QUBIT SIZE: {n_qubits}")
    print(f"{'#'*80}")

    for algo_name in ALGORITHMS:
        print(f"\n  === {algo_name}_{n_qubits} ===")

        for rep_idx, seed in enumerate(SEEDS):
            rep_label = f"rep{rep_idx}"
            coupling_map = [[i, i + 1] for i in range(n_qubits - 1)]
            arch_edges = [(i, i + 1) for i in range(n_qubits - 1)]

            # --- QISKIT ---
            t0 = time.time()
            try:
                qc = CIRCUIT_GENERATORS[algo_name]["qiskit"](n_qubits)
                engine = DeterministicSearchEngine(search_space=QiskitSS(
                    optimization_levels=(0, 1, 2, 3),
                    layout_methods=("trivial", "sabre"),
                    routing_methods=("basic", "sabre"),
                    seeds=(seed,),
                ))
                result = engine.search(qc, challenge_id=f"{algo_name}_{n_qubits}_qiskit_{rep_label}",
                                       basis_gates=["cx", "u3"], coupling_map=coupling_map)
                for c in result.candidates:
                    if c.compile_success and c.metrics.get("depth") is not None:
                        all_observations.append({
                            "n_qubits": n_qubits,
                            "algorithm": algo_name,
                            "framework": "qiskit",
                            "config_id": c.candidate_id,
                            "replicate": rep_label,
                            "depth": c.metrics["depth"],
                            "size": c.metrics["size"],
                            "two_qubit_gates": c.metrics.get("two_qubit_gates", 0),
                        })
                elapsed = time.time() - t0
                timing_data[f"{algo_name}_{n_qubits}"]["qiskit"] = elapsed
                print(f"    qiskit  {rep_label}: {len(result.candidates)} cand, {elapsed:.1f}s")
            except Exception as e:
                print(f"    qiskit  {rep_label}: ERROR: {e}")

            # --- PYTKET (convert from qiskit) ---
            t0 = time.time()
            try:
                from pytket.extensions.qiskit import qiskit_to_tk
                qc = CIRCUIT_GENERATORS[algo_name]["qiskit"](n_qubits)
                tk = qiskit_to_tk(qc)
                search = PytketSequentialSearch(beam_width=3)
                tk_result = search.run(tk, challenge_id=f"{algo_name}_{n_qubits}_pytket_{rep_label}",
                                       context={"architecture_edges": arch_edges})
                for s in tk_result.states:
                    ev = s.evaluation
                    if ev is not None and ev.success and ev.metrics.get("depth") is not None:
                        all_observations.append({
                            "n_qubits": n_qubits,
                            "algorithm": algo_name,
                            "framework": "pytket",
                            "config_id": s.state_id,
                            "replicate": rep_label,
                            "depth": ev.metrics["depth"],
                            "size": ev.metrics.get("n_gates", 0),
                            "two_qubit_gates": ev.metrics.get("two_qubit_gates", 0),
                        })
                elapsed = time.time() - t0
                timing_data[f"{algo_name}_{n_qubits}"]["pytket"] = elapsed
                print(f"    pytket  {rep_label}: {len(tk_result.states)} states, {elapsed:.1f}s")
            except Exception as e:
                print(f"    pytket  {rep_label}: ERROR: {e}")

            # --- PENNYLANE ---
            t0 = time.time()
            try:
                tape = CIRCUIT_GENERATORS[algo_name]["pennylane"](n_qubits)
                pl_search = PennyLaneSequentialSearch(beam_width=3)
                pl_result = pl_search.run(tape, challenge_id=f"{algo_name}_{n_qubits}_pl_{rep_label}")
                for s in pl_result.states:
                    ev = s.evaluation
                    if ev is not None and ev.success:
                        size = ev.metrics.get("n_operations", 0)
                        if size > 0:
                            all_observations.append({
                                "n_qubits": n_qubits,
                                "algorithm": algo_name,
                                "framework": "pennylane",
                                "config_id": s.state_id,
                                "replicate": rep_label,
                                "depth": ev.metrics.get("depth", 0),
                                "size": size,
                                "two_qubit_gates": ev.metrics.get("two_qubit_gates", 0),
                            })
                elapsed = time.time() - t0
                timing_data[f"{algo_name}_{n_qubits}"]["pennylane"] = elapsed
                print(f"    pennylane {rep_label}: {len(pl_result.states)} states, {elapsed:.1f}s")
            except Exception as e:
                print(f"    pennylane {rep_label}: ERROR: {e}")

            # --- CIRQ ---
            t0 = time.time()
            try:
                cirq_circuit = CIRCUIT_GENERATORS[algo_name]["cirq"](n_qubits)
                cirq_search = CirqSequentialSearch(beam_width=3)
                cirq_result = cirq_search.run(cirq_circuit, challenge_id=f"{algo_name}_{n_qubits}_cirq_{rep_label}")
                for s in cirq_result.states:
                    ev = s.evaluation
                    if ev is not None and ev.success and ev.metrics.get("n_moments") is not None:
                        all_observations.append({
                            "n_qubits": n_qubits,
                            "algorithm": algo_name,
                            "framework": "cirq",
                            "config_id": s.state_id,
                            "replicate": rep_label,
                            "depth": ev.metrics["n_moments"],
                            "size": ev.metrics["n_operations"],
                            "two_qubit_gates": ev.metrics.get("two_qubit_gates", 0),
                        })
                elapsed = time.time() - t0
                timing_data[f"{algo_name}_{n_qubits}"]["cirq"] = elapsed
                print(f"    cirq    {rep_label}: {len(cirq_result.states)} states, {elapsed:.1f}s")
            except Exception as e:
                print(f"    cirq    {rep_label}: ERROR: {e}")

    # Save incrementally
    with open("/tmp/scale_observations_v2.json", "w") as f:
        json.dump({"observations": all_observations, "timing": dict(timing_data)}, f, indent=2, default=str)
    print(f"\n  [Saved {len(all_observations)} observations so far]")

# ===========================================================================
# Save final
# ===========================================================================
with open("/tmp/scale_observations_v2.json", "w") as f:
    json.dump({"observations": all_observations, "timing": dict(timing_data)}, f, indent=2, default=str)
print(f"\n\nTotal observations: {len(all_observations)}")
print(f"Saved to /tmp/scale_observations_v2.json")
