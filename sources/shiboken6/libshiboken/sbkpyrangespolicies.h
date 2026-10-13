// Copyright (C) 2026 The Qt Company Ltd.
// SPDX-License-Identifier: LicenseRef-Qt-Commercial OR LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only
// Qt-Security score:significant reason:default

#ifndef SBKPYRANGESPOLICIES_H
#define SBKPYRANGESPOLICIES_H

#include "autodecref.h"
#include "shibokenclasshelpermacros.h"
#ifdef Py_GIL_DISABLED
#  include "sbkpep.h"
#endif

#include <cassert>

// Internal
namespace Shiboken::Detail {

// Life time/ownership policies for PyTupleRangeT: Default: raw pointer/non-owning, trivially copyable, zero cost
struct PyRangeDefaultLifetimePolicy
{
    explicit PyRangeDefaultLifetimePolicy(PyObject *) noexcept {}
};

// AutoDecRef-based life time policy (keep a reference).
struct AutoDecRefLifetimePolicy : public Shiboken::AutoDecRef
{
    explicit AutoDecRefLifetimePolicy(PyObject *o) noexcept : Shiboken::AutoDecRef(Py_XNewRef(o)) {}
};

#ifdef Py_GIL_DISABLED
// Keeps a copy of the dict (PepDict_IterationSnapshot()) for the range to
// iterate, so that another thread changing the dict cannot free the borrowed
// items. If copying fails, the range iterates the dict itself.
struct DictSnapshotLifetimePolicy : public Shiboken::AutoDecRef
{
    explicit DictSnapshotLifetimePolicy(PyObject *dict) noexcept
        : Shiboken::AutoDecRef(dict != nullptr ? PepDict_IterationSnapshot(dict) : nullptr)
    {
        if (dict != nullptr && isNull()) {
            PyErr_Clear();
            reset(Py_NewRef(dict));
        }
    }
};

class CriticalSectionLifetimePolicy
{
public:
    LIBSHIBOKEN_DISABLE_COPY_MOVE(CriticalSectionLifetimePolicy)

    explicit CriticalSectionLifetimePolicy(PyObject *obj) noexcept
    {
        assert(obj != nullptr);
        PyCriticalSection_Begin(&m_cs, obj);
    }

    ~CriticalSectionLifetimePolicy()
    {
        PyCriticalSection_End(&m_cs);
    }

private:
    PyCriticalSection m_cs;
};
#endif // Py_GIL_DISABLED

} // namespace Shiboken::Detail

#endif // SBKPYRANGESPOLICIES_H
