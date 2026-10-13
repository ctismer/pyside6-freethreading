// Copyright (C) 2026 The Qt Company Ltd.
// SPDX-License-Identifier: LicenseRef-Qt-Commercial OR LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only
// Qt-Security score:significant reason:default

#ifndef SBK_ACQUIREDWRAPPER_H
#define SBK_ACQUIREDWRAPPER_H

#include "sbkpython.h"

#ifdef Py_GIL_DISABLED

#include "shibokenclasshelpermacros.h"

#include <utility>

struct SbkObject;

namespace Shiboken
{

class BindingManager;

class AcquiredWrapper
{
public:
    AcquiredWrapper() noexcept = default;
    LIBSHIBOKEN_DISABLE_COPY(AcquiredWrapper)

    AcquiredWrapper(AcquiredWrapper &&o) noexcept : m_obj(std::exchange(o.m_obj, nullptr)) {}
    AcquiredWrapper &operator=(AcquiredWrapper &&o) noexcept
    {
        if (this != &o) {
            reset();
            m_obj = std::exchange(o.m_obj, nullptr);
        }
        return *this;
    }

    ~AcquiredWrapper() { reset(); }

    // Deleted on temporaries: the pointer must not outlive the reference
    [[nodiscard]] SbkObject *object() const & noexcept { return m_obj; }
    SbkObject *object() const && = delete;
    [[nodiscard]] PyObject *pyObject() const & noexcept
    { return reinterpret_cast<PyObject *>(m_obj); }
    PyObject *pyObject() const && = delete;
    [[nodiscard]] bool isNull() const noexcept { return m_obj == nullptr; }

    explicit operator bool() const noexcept { return m_obj != nullptr; }

    [[nodiscard]] SbkObject *release() noexcept { return std::exchange(m_obj, nullptr); }

    void reset() noexcept
    {
        Py_XDECREF(reinterpret_cast<PyObject *>(std::exchange(m_obj, nullptr)));
    }

private:
    friend class BindingManager;
    static AcquiredWrapper fromOwned(SbkObject *obj) noexcept { return AcquiredWrapper(obj); }

    explicit AcquiredWrapper(SbkObject *obj) noexcept : m_obj(obj) {}

    SbkObject *m_obj = nullptr;
};

} // namespace Shiboken

#endif // Py_GIL_DISABLED

#endif // SBK_ACQUIREDWRAPPER_H
